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

from django.db import transaction
from billing.models import Wallet, LedgerTransaction
from .authentication import UniversalOrJWTAuthentication

class UniversalInferenceAPIView(APIView):
    """
    POST /api/v1/inference/@<username>/<model_name>/
    The monetized universal gateway.
    """
    authentication_classes = [UniversalOrJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "predict"

    def post(self, request, username, model_name):
        # 1. Look up Model
        model = Model.objects.filter(owner__username=username, name=model_name).first()
        if not model:
            return Response({"error": "Model not found"}, status=status.HTTP_404_NOT_FOUND)
            
        if not model.is_public and model.owner != request.user:
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        # 2. Look up running deployment (For Phase 4, we assume the latest deployment)
        deployment = Deployment.objects.select_related("model_version").filter(
            model_version__model=model,
            status=Deployment.Status.RUNNING,
            internal_url__isnull=False
        ).order_by("-created_at").first()

        if not deployment:
            return Response({"error": "No running deployment available for this model"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # 3. Check Wallet Balance
        consumer_wallet, _ = Wallet.objects.get_or_create(user=request.user)
        cost = model.cost_per_run
        
        if consumer_wallet.credit_balance < cost:
            return Response(
                {"error": "Insufficient credits", "balance": consumer_wallet.credit_balance, "cost": cost}, 
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

        # 4. Perform Inference (Synchronous for now)
        serializer = PredictRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instances = serializer.validated_data["instances"]

        manifest_path = Path(deployment.model_version.artifact_path) / "model.yaml"
        runner = RunnerFactory.get_runner(framework=model.framework)

        start = time.time()
        try:
            result = runner.predict({
                "model_id": str(model.id),
                "manifest_path": str(manifest_path),
                "instances": instances,
            })
            
            latency = (time.time() - start) * 1000
            if result.status_code >= 400:
                # If inference fails, do NOT charge the user
                return Response(result.data, status=result.status_code)

        except Exception as e:
            return Response({"error": "Inference execution failed", "detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 5. Inference Succeeded -> Finalize Billing
        with transaction.atomic():
            # Lock the wallets to prevent race conditions
            consumer_wallet = Wallet.objects.select_for_update().get(user=request.user)
            creator_wallet, _ = Wallet.objects.select_for_update().get_or_create(user=model.owner)

            creator_cut = cost * type(cost)('0.8')
            platform_cut = cost - creator_cut

            # Deduct from consumer
            consumer_wallet.credit_balance -= cost
            consumer_wallet.lifetime_spent += cost
            consumer_wallet.save()

            # Add to creator
            creator_wallet.credit_balance += creator_cut
            creator_wallet.lifetime_earned += creator_cut
            creator_wallet.save()

            # Record Ledger
            LedgerTransaction.objects.create(
                consumer=request.user,
                creator=model.owner,
                model=model,
                transaction_type=LedgerTransaction.TransactionType.INFERENCE,
                amount=cost,
                creator_share=creator_cut,
                platform_share=platform_cut,
                description=f"Inference on {model.name}"
            )
            
            # Log Prediction
            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data=result.data,
                latency_ms=latency,
                status="SUCCESS"
            )

        return Response(result.data, status=result.status_code)
