import time
import requests
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from deployments.models import Deployment
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

        serializer = PredictRequestSerializer(data={"payload": request.data})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data["payload"]

        start = time.time()
        try:
            result, upstream_status = self._forward_to_container(deployment.internal_url, data)
            latency = (time.time() - start) * 1000

            log_status = "SUCCESS" if upstream_status < 400 else "ERROR"
            err_msg = None
            if upstream_status >= 400:
                err_msg = str(result.get("error") or result.get("detail") or "Upstream client error")

            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=deployment,
                input_data=data,
                output_data=result,
                latency_ms=latency,
                status=log_status,
                error_message=err_msg,
            )
            return Response(result, status=upstream_status)

        except requests.Timeout:
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
                error_message="Upstream inference timed out",
            )
            return Response({"error": "Upstream inference timed out"}, status=status.HTTP_504_GATEWAY_TIMEOUT)

        except requests.ConnectionError:
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
            return Response({"error": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _forward_to_container(self, base_url: str, payload: dict):
        timeout_seconds = int(getattr(settings, "INFERENCE_TIMEOUT_SECONDS", 15))
        url = f"{base_url.rstrip('/')}/predict"
        response = requests.post(url, json=payload, timeout=timeout_seconds)

        if response.status_code >= 500:
            raise requests.ConnectionError("Upstream container returned server error")

        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {"raw": response.text}

        return data, response.status_code