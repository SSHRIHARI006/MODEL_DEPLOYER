from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
import requests
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import LedgerTransaction, Wallet
from core.errors import error_response, internal_error_response, log_exception
from core.throttling import ConfigurableScopedRateThrottle
from deployments.models import Deployment
from model_registry.manifest import validate_prediction_instances
from model_registry.models import Model
from runners.factory import RunnerFactory

from .authentication import UniversalOrJWTAuthentication
from .models import PredictionLog
from .permissions import HasValidModelAPIKey
from .serializers import PredictRequestSerializer
from .singleflight import single_flight


def prediction_cache_key(model_id, model_version_id, instances):
    payload = json.dumps(
        {
            "model_id": str(model_id),
            "model_version_id": str(model_version_id),
            "instances": instances,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"prediction:{settings.PREDICTION_CACHE_VERSION}:{digest}"


def _debit_credits(consumer, creator, model, amount: Decimal, description: str):
    """BILL-01: Atomically debits consumer and credits creator, ordering locks by pk to prevent deadlocks."""
    with transaction.atomic():
        c_w, _ = Wallet.objects.get_or_create(user=consumer)
        m_w, _ = Wallet.objects.get_or_create(user=creator)
        # Lock in deterministic PK order to eliminate deadlocks
        locked = {
            w.pk: w
            for w in Wallet.objects.filter(pk__in=[c_w.pk, m_w.pk])
            .select_for_update()
            .order_by("pk")
        }
        consumer_wallet = locked[c_w.pk]
        creator_wallet = locked[m_w.pk]

        if consumer_wallet.credit_balance < amount:
            return None, consumer_wallet.credit_balance

        consumer_wallet.credit_balance -= amount
        consumer_wallet.lifetime_spent += amount
        consumer_wallet.save(
            update_fields=["credit_balance", "lifetime_spent", "updated_at"]
        )

        creator_wallet.credit_balance += amount
        creator_wallet.lifetime_earned += amount
        creator_wallet.save(
            update_fields=["credit_balance", "lifetime_earned", "updated_at"]
        )

        tx = LedgerTransaction.objects.create(
            consumer=consumer,
            creator=creator,
            model=model,
            transaction_type=LedgerTransaction.TransactionType.INFERENCE,
            amount=amount,
            description=description,
        )
        return tx, consumer_wallet.credit_balance


def _refund_credits(
    consumer,
    creator,
    model,
    amount: Decimal,
    reference_tx_id: str,
    description: str,
):
    """BILL-01: Atomically refunds consumer from creator with deterministic locking order."""
    with transaction.atomic():
        c_w = Wallet.objects.get(user=consumer)
        m_w = Wallet.objects.get(user=creator)
        locked = {
            w.pk: w
            for w in Wallet.objects.filter(pk__in=[c_w.pk, m_w.pk])
            .select_for_update()
            .order_by("pk")
        }
        consumer_wallet = locked[c_w.pk]
        creator_wallet = locked[m_w.pk]

        consumer_wallet.credit_balance += amount
        consumer_wallet.lifetime_spent -= amount
        consumer_wallet.save(
            update_fields=["credit_balance", "lifetime_spent", "updated_at"]
        )

        creator_wallet.credit_balance -= amount
        creator_wallet.lifetime_earned -= amount
        creator_wallet.save(
            update_fields=["credit_balance", "lifetime_earned", "updated_at"]
        )

        return LedgerTransaction.objects.create(
            consumer=consumer,
            creator=creator,
            model=model,
            transaction_type=LedgerTransaction.TransactionType.REFUND,
            amount=amount,
            reference_id=reference_tx_id,
            description=description,
        )


class PredictAPIView(APIView):
    permission_classes = [IsAuthenticated, HasValidModelAPIKey]
    throttle_classes = [ConfigurableScopedRateThrottle]
    throttle_scope = "predict"

    def post(self, request, model_id):
        start_req = time.time()
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
            return error_response(
                code="DEPLOYMENT_NOT_AVAILABLE",
                message="No running deployment available for this model",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                request=request,
            )

        serializer = PredictRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instances = serializer.validated_data["instances"]

        # API-01 / API-04: Row consistency and shape validation
        try:
            validate_prediction_instances(instances)
        except ValueError as err:
            return error_response(
                code="INVALID_INPUT",
                message=str(err),
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request,
            )

        cache_key = prediction_cache_key(
            model.id, deployment.model_version_id, instances
        )

        def safe_get_cache(k: str):
            try:
                return cache.get(k)
            except Exception:
                return None

        # Check cache directly first
        cached_data = safe_get_cache(cache_key)
        if cached_data is not None:
            gate_ms = (time.time() - start_req) * 1000.0
            PredictionLog.objects.create(
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data=cached_data,
                latency_ms=gate_ms,
                gateway_latency_ms=gate_ms,
                runner_compute_ms=None,
                cache_hit=True,
                status="SUCCESS",
            )
            return Response(cached_data, status=status.HTTP_200_OK)

        base_path = deployment.model_version.artifact_path
        if base_path.startswith("s3://"):
            manifest_path = f"{base_path}/model.yaml"
        else:
            manifest_path = str(Path(base_path) / "model.yaml")
        runner = RunnerFactory.get_runner(framework=model.framework)

        def do_predict():
            t0 = time.time()
            res = runner.predict(
                {
                    "model_id": str(deployment.model_version_id),
                    "manifest_path": str(manifest_path),
                    "instances": instances,
                }
            )
            c_ms = (time.time() - t0) * 1000.0
            return res, c_ms

        try:
            flight_res, was_cached = single_flight.execute(
                cache_key=cache_key,
                execute_fn=do_predict,
                get_cache_fn=safe_get_cache,
            )

            gate_ms = (time.time() - start_req) * 1000.0

            if was_cached:
                PredictionLog.objects.create(
                    user=request.user,
                    model=model,
                    deployment=deployment,
                    input_data={"instances": instances},
                    output_data=flight_res,
                    latency_ms=gate_ms,
                    gateway_latency_ms=gate_ms,
                    runner_compute_ms=None,
                    cache_hit=True,
                    status="SUCCESS",
                )
                return Response(flight_res, status=status.HTTP_200_OK)

            result, compute_ms = flight_res
            upstream_status = result.status_code

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
                else:
                    try:
                        cache.set(
                            cache_key,
                            data,
                            timeout=settings.PREDICTION_CACHE_TTL_SECONDS,
                        )
                    except Exception:
                        pass

            PredictionLog.objects.create(
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data=data,
                latency_ms=gate_ms,
                gateway_latency_ms=gate_ms,
                runner_compute_ms=compute_ms,
                cache_hit=False,
                status=log_status,
                error_message=err_msg,
            )
            return Response(data, status=upstream_status)

        except requests.Timeout:
            gate_ms = (time.time() - start_req) * 1000.0
            PredictionLog.objects.create(
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data={},
                latency_ms=gate_ms,
                gateway_latency_ms=gate_ms,
                runner_compute_ms=None,
                cache_hit=False,
                status="ERROR",
                error_message="Upstream inference timed out",
            )
            return error_response(
                code="INFERENCE_TIMEOUT",
                message="Upstream inference timed out",
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                request=request,
            )

        except requests.ConnectionError:
            gate_ms = (time.time() - start_req) * 1000.0
            PredictionLog.objects.create(
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data={},
                latency_ms=gate_ms,
                gateway_latency_ms=gate_ms,
                runner_compute_ms=None,
                cache_hit=False,
                status="ERROR",
                error_message="Upstream deployment unavailable",
            )
            return error_response(
                code="DEPLOYMENT_UNAVAILABLE",
                message="Upstream deployment unavailable",
                status_code=status.HTTP_502_BAD_GATEWAY,
                request=request,
            )

        except Exception as exc:
            # SEC-06: keep the raw exception out of the response and the log row
            gate_ms = (time.time() - start_req) * 1000.0
            PredictionLog.objects.create(
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data={},
                latency_ms=gate_ms,
                gateway_latency_ms=gate_ms,
                runner_compute_ms=None,
                cache_hit=False,
                status="ERROR",
                error_message="Internal server error",
            )
            log_exception("prediction failed", exc, request=request)
            return internal_error_response(request=request, code="PREDICTION_FAILED")


class UniversalInferenceAPIView(APIView):
    """POST /api/v1/inference/@<username>/<model_name>/

    The monetized universal gateway.
    BILL-01: Atomic reserve before inference, refund on error, cache-hit discount.
    """

    authentication_classes = [UniversalOrJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ConfigurableScopedRateThrottle]
    throttle_scope = "predict"

    def post(self, request, username, model_name):
        start_req = time.time()

        # 1. Look up Model
        model = Model.objects.filter(owner__username=username, name=model_name).first()
        if not model:
            return error_response(
                code="MODEL_NOT_FOUND",
                message="Model not found",
                status_code=status.HTTP_404_NOT_FOUND,
                request=request,
            )

        if not model.is_public and model.owner != request.user:
            return error_response(
                code="FORBIDDEN",
                message="Forbidden",
                status_code=status.HTTP_403_FORBIDDEN,
                request=request,
            )

        # 2. Look up running deployment
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
            return error_response(
                code="DEPLOYMENT_NOT_AVAILABLE",
                message="No running deployment available for this model",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                request=request,
            )

        # 3. Validate instances
        serializer = PredictRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instances = serializer.validated_data["instances"]

        try:
            validate_prediction_instances(instances)
        except ValueError as err:
            return error_response(
                code="INVALID_INPUT",
                message=str(err),
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request,
            )

        # 4. BILL-01: Up-front reservation
        cost = model.cost_per_run
        billing_enabled = getattr(settings, "BILLING_ENABLED", True)
        is_free = (request.user == model.owner) or not billing_enabled or (cost == 0)
        effective_cost = Decimal("0") if is_free else Decimal(str(cost))
        debit_tx = None

        if not is_free:
            debit_tx, current_balance = _debit_credits(
                consumer=request.user,
                creator=model.owner,
                model=model,
                amount=effective_cost,
                description=f"Inference reservation on {model.name}",
            )
            if debit_tx is None:
                return Response(
                    {
                        "error": "Insufficient credits",
                        "code": "INSUFFICIENT_CREDITS",
                        "balance": current_balance,
                        "cost": effective_cost,
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )

        cache_key = prediction_cache_key(
            model.id, deployment.model_version_id, instances
        )
        try:
            cached_data = cache.get(cache_key)
        except Exception:
            cached_data = None

        if cached_data is not None:
            result_data = cached_data
            result_status = status.HTTP_200_OK
            was_cache_hit = True
            runner_compute_ms = None
            gate_ms = (time.time() - start_req) * 1000.0

            # BILL-01: 50% discount refund on cache hit
            if debit_tx and effective_cost > 0:
                discount_refund = effective_cost * Decimal("0.5")
                _refund_credits(
                    consumer=request.user,
                    creator=model.owner,
                    model=model,
                    amount=discount_refund,
                    reference_tx_id=str(debit_tx.id),
                    description=f"50% cache hit discount on {model.name}",
                )

            PredictionLog.objects.create(
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data=result_data,
                latency_ms=gate_ms,
                gateway_latency_ms=gate_ms,
                runner_compute_ms=None,
                cache_hit=True,
                status="SUCCESS",
            )
            return Response(result_data, status=result_status)

        # Cold inference execution
        base_path = deployment.model_version.artifact_path
        if base_path.startswith("s3://"):
            manifest_path = f"{base_path}/model.yaml"
        else:
            manifest_path = str(Path(base_path) / "model.yaml")

        runner = RunnerFactory.get_runner(framework=model.framework)
        start = time.time()
        try:
            result = runner.predict(
                {
                    "model_id": str(deployment.model_version_id),
                    "manifest_path": manifest_path,
                    "instances": instances,
                }
            )
        except Exception as exc:
            # BILL-01: 100% refund on unhandled runner exception
            if debit_tx:
                _refund_credits(
                    consumer=request.user,
                    creator=model.owner,
                    model=model,
                    amount=effective_cost,
                    reference_tx_id=str(debit_tx.id),
                    description=f"Refund for failed inference on {model.name}",
                )
            log_exception("runner call failed", exc, request=request)
            return internal_error_response(request=request, code="INFERENCE_FAILED")

        runner_compute_ms = (time.time() - start) * 1000.0
        gate_ms = (time.time() - start_req) * 1000.0

        if result.status_code >= 400:
            # BILL-01: 100% refund on runner failure response
            if debit_tx:
                _refund_credits(
                    consumer=request.user,
                    creator=model.owner,
                    model=model,
                    amount=effective_cost,
                    reference_tx_id=str(debit_tx.id),
                    description=f"Refund for failed inference on {model.name}",
                )
            PredictionLog.objects.create(
                user=request.user,
                model=model,
                deployment=deployment,
                input_data={"instances": instances},
                output_data=result.data,
                latency_ms=gate_ms,
                gateway_latency_ms=gate_ms,
                runner_compute_ms=runner_compute_ms,
                cache_hit=False,
                status="ERROR",
                error_message=str(result.data.get("error", "Inference error")),
            )
            return Response(result.data, status=result.status_code)

        result_data = result.data
        result_status = result.status_code
        try:
            cache.set(
                cache_key,
                result_data,
                timeout=settings.PREDICTION_CACHE_TTL_SECONDS,
            )
        except Exception:
            pass

        PredictionLog.objects.create(
            user=request.user,
            model=model,
            deployment=deployment,
            input_data={"instances": instances},
            output_data=result_data,
            latency_ms=gate_ms,
            gateway_latency_ms=gate_ms,
            runner_compute_ms=runner_compute_ms,
            cache_hit=False,
            status="SUCCESS",
        )

        return Response(result_data, status=result_status)
