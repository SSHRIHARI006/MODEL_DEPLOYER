import time
import requests
from django.conf import settings
from pathlib import Path
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from deployments.models import Deployment
from runners.factory import RunnerFactory
from model_registry.models import Model
from .models import PredictionLog
from .permissions import HasValidModelAPIKey
from .serializers import PredictRequestSerializer


class PredictAPIView(APIView):
    permission_classes = [IsAuthenticated, HasValidModelAPIKey]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "predict"

    def post(self, request, model_id):
        model = get_object_or_404(Model, id=model_id)

        deployment = (
            Deployment.objects.select_related("model_version")
            .filter(
                model_version__model=model,
                status=Deployment.Status.RUNNING,
                internal_url__isnull=False,
            )
            .order_by("-created_at")
            .first()
        )
        if not deployment:
            return Response(
                {"error": "No running deployment available for this model"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = PredictRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instances = serializer.validated_data["instances"]

        manifest_path = Path(deployment.model_version.artifact_path) / "model.yaml"
        runner = RunnerFactory.get_runner(framework=model.framework)

        start = time.time()
        try:
            result = runner.predict(
                {
                    "model_id": str(model.id),
                    "manifest_path": str(manifest_path),
                    "instances": instances,
                }
            )
            upstream_status = result.status_code
            latency = (time.time() - start) * 1000

            if upstream_status >= 500:
                upstream_status = status.HTTP_502_BAD_GATEWAY
                data = {"error": result.data.get("error") or "Upstream runner error"}
                log_status = "ERROR"
                err_msg = data["error"]
            else:
                data = result.data
                log_status = "SUCCESS" if upstream_status < 400 else "ERROR"
                err_msg = None
                if upstream_status >= 400:
                    err_msg = str(
                        data.get("error")
                        or data.get("detail")
                        or "Upstream client error"
                    )

            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data=data,
                latency_ms=latency,
                status=log_status,
                error_message=err_msg,
            )
            return Response(data, status=upstream_status)

        except requests.Timeout:
            latency = (time.time() - start) * 1000
            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data={},
                latency_ms=latency,
                status="ERROR",
                error_message="Upstream inference timed out",
            )
            return Response(
                {"error": "Upstream inference timed out"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        except requests.ConnectionError:
            latency = (time.time() - start) * 1000
            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data={},
                latency_ms=latency,
                status="ERROR",
                error_message="Upstream deployment unavailable",
            )
            return Response(
                {"error": "Upstream deployment unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=deployment,
                input_data=data,
                output_data={},
                latency_ms=latency,
                status="ERROR",
                error_message=str(e),
            )
            error_msg = str(e) if settings.DEBUG else "Internal server error"
            return Response(
                {"error": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
