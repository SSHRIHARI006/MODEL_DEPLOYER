from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from django.db.models import Avg, Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.models import APIKey
from deployments.models import Deployment
from model_registry.models import Model
from prediction_gateway.models import PredictionLog

User = get_user_model()


def calculate_percentile(sorted_values: list[float], p: float) -> float:
    """OBS-01: Linear interpolation percentile calculation (matches numpy standard)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = f + 1
    if c < len(sorted_values):
        return float(sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f]))
    return float(sorted_values[f])


def _compute_metrics(source: QuerySet | list[Any]) -> dict[str, Any]:
    """OBS-01: Aggregates metrics using SQL aggregates when given a QuerySet,
    distinguishing gateway latency from compute latency and tracking cache hits.
    """
    if isinstance(source, QuerySet):
        agg = source.aggregate(
            total_requests=Count("id"),
            success_count=Count("id", filter=Q(status="SUCCESS")),
            error_count=Count("id", filter=Q(status="ERROR")),
            cache_hits=Count("id", filter=Q(cache_hit=True)),
            avg_gateway_latency=Avg("gateway_latency_ms"),
            avg_compute_latency=Avg("runner_compute_ms", filter=Q(cache_hit=False)),
        )
        total = agg["total_requests"] or 0
        if total == 0:
            return {
                "total_requests": 0,
                "success_count": 0,
                "error_count": 0,
                "cache_hits": 0,
                "cache_hit_ratio": 0.0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "avg_compute_latency_ms": 0.0,
                "p95_compute_latency_ms": 0.0,
            }

        success_count = agg["success_count"] or 0
        error_count = agg["error_count"] or 0
        cache_hits = agg["cache_hits"] or 0

        # Query bounded value lists for p95 computation to avoid in-memory bloat
        gateway_lats = sorted(
            float(v) for v in source.exclude(gateway_latency_ms__isnull=True).values_list("gateway_latency_ms", flat=True)[:5000]
        )
        if not gateway_lats:
            gateway_lats = sorted(
                float(v) for v in source.exclude(latency_ms__isnull=True).values_list("latency_ms", flat=True)[:5000]
            )

        compute_lats = sorted(
            float(v) for v in source.filter(cache_hit=False).exclude(runner_compute_ms__isnull=True).values_list("runner_compute_ms", flat=True)[:5000]
        )

        avg_lat = round(agg["avg_gateway_latency"] or (mean(gateway_lats) if gateway_lats else 0.0), 3)
        avg_comp = round(agg["avg_compute_latency"] or (mean(compute_lats) if compute_lats else 0.0), 3)

        return {
            "total_requests": total,
            "success_count": success_count,
            "error_count": error_count,
            "cache_hits": cache_hits,
            "cache_hit_ratio": round(cache_hits / total, 4),
            "success_rate": round((success_count / total) * 100, 2),
            "avg_latency_ms": avg_lat,
            "p95_latency_ms": round(calculate_percentile(gateway_lats, 0.95), 3),
            "avg_compute_latency_ms": avg_comp,
            "p95_compute_latency_ms": round(calculate_percentile(compute_lats, 0.95), 3),
        }

    # Fallback when source is a Python list of model instances
    logs = source
    total_requests = len(logs)
    success_count = sum(1 for log in logs if getattr(log, "status", None) == "SUCCESS")
    error_count = sum(1 for log in logs if getattr(log, "status", None) == "ERROR")
    cache_hits = sum(1 for log in logs if getattr(log, "cache_hit", False))

    if total_requests == 0:
        return {
            "total_requests": 0,
            "success_count": 0,
            "error_count": 0,
            "cache_hits": 0,
            "cache_hit_ratio": 0.0,
            "success_rate": 0.0,
            "avg_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "avg_compute_latency_ms": 0.0,
            "p95_compute_latency_ms": 0.0,
        }

    gateway_lats = sorted(
        float(getattr(log, "gateway_latency_ms", None) or getattr(log, "latency_ms", 0) or 0)
        for log in logs
    )
    compute_lats = sorted(
        float(getattr(log, "runner_compute_ms", None) or 0)
        for log in logs
        if not getattr(log, "cache_hit", False) and getattr(log, "runner_compute_ms", None) is not None
    )

    return {
        "total_requests": total_requests,
        "success_count": success_count,
        "error_count": error_count,
        "cache_hits": cache_hits,
        "cache_hit_ratio": round(cache_hits / total_requests, 4),
        "success_rate": round((success_count / total_requests) * 100, 2),
        "avg_latency_ms": round(mean(gateway_lats), 3) if gateway_lats else 0.0,
        "p95_latency_ms": round(calculate_percentile(gateway_lats, 0.95), 3),
        "avg_compute_latency_ms": round(mean(compute_lats), 3) if compute_lats else 0.0,
        "p95_compute_latency_ms": round(calculate_percentile(compute_lats, 0.95), 3),
    }


class HealthAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        db_ok = True
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            db_ok = False

        return Response(
            {
                "status": "ok" if db_ok else "degraded",
                "database": "up" if db_ok else "down",
                "timestamp": timezone.now(),
            },
            status=200 if db_ok else 503,
        )


class ReadyHealthAPIView(APIView):
    """OBS-03: Readiness probe — checks Database, Redis cache, and Runner readiness."""

    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        db_ok = True
        redis_ok = True
        runner_ok = True

        # 1. Database check
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            db_ok = False

        # 2. Redis/Cache check
        try:
            cache.set("_ready_ping", "1", timeout=5)
            redis_ok = (cache.get("_ready_ping") == "1")
        except Exception:
            redis_ok = False

        # 3. Runner check
        runner_url = getattr(settings, "RUNNER_BASE_URL", "http://127.0.0.1:8001")
        import requests
        try:
            r = requests.get(f"{runner_url.rstrip('/')}/health", timeout=2.0)
            runner_ok = (r.status_code == 200)
        except Exception:
            runner_ok = False

        is_ready = db_ok and redis_ok and runner_ok
        status_code = 200 if is_ready else 503

        return Response(
            {
                "status": "ready" if is_ready else "degraded",
                "database": "up" if db_ok else "down",
                "redis": "up" if redis_ok else "down",
                "runner": "up" if runner_ok else "down",
                "timestamp": timezone.now(),
            },
            status=status_code,
        )


class LiveHealthAPIView(APIView):
    """OBS-03: Lightweight liveness probe — no DB, no Redis, no storage checks.

    Used by orchestrators/probes to confirm the API process is alive and
    serving requests without placing load on backing services.
    """

    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        return Response({"status": "alive"}, status=200)


class MetricsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = PredictionLog.objects.filter(user=request.user)
        return Response(_compute_metrics(queryset))


class ModelMetricsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, model_id):
        model = get_object_or_404(Model, id=model_id, owner=request.user)
        queryset = PredictionLog.objects.filter(user=request.user, model=model)
        data = _compute_metrics(queryset)

        latest_version = model.versions.order_by("-created_at").first()
        latest_deployment = None
        if latest_version:
            latest_deployment = (
                Deployment.objects.filter(model_version=latest_version)
                .order_by("-created_at")
                .first()
            )

        data.update(
            {
                "model_id": str(model.id),
                "model_name": model.name,
                "framework": model.framework,
                "latest_version": latest_version.version if latest_version else None,
                "latest_version_id": str(latest_version.id) if latest_version else None,
                "latest_deployment_status": latest_deployment.status if latest_deployment else "NOT_DEPLOYED",
                "latest_deployment_id": str(latest_deployment.id) if latest_deployment else None,
                "latest_deployment_error": latest_deployment.last_error if latest_deployment else None,
                "latest_deployment_error_code": latest_deployment.last_error_code if latest_deployment else None,
                "latest_deployment_attempt": latest_deployment.build_attempt if latest_deployment else 0,
                "latest_deployment_task_id": latest_deployment.celery_task_id if latest_deployment else None,
                "latest_deployment_created_at": latest_deployment.created_at if latest_deployment else None,
                "latest_deployment_stopped_at": latest_deployment.stopped_at if latest_deployment else None,
                "latest_deployment_logs": latest_deployment.build_logs if latest_deployment else None,
            }
        )
        return Response(data)


class StaffGlobalMetricsAPIView(APIView):
    """OBS-02: Staff-only global telemetry endpoint."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        deployments_by_status = defaultdict(int)
        for row in Deployment.objects.values("status").annotate(count=Count("id")):
            deployments_by_status[row["status"]] = row["count"]

        global_metrics = _compute_metrics(PredictionLog.objects.all())

        return Response(
            {
                "total_users": User.objects.count(),
                "total_models": Model.objects.count(),
                "deployments": {
                    "running": deployments_by_status.get(Deployment.Status.RUNNING, 0),
                    "building": deployments_by_status.get(Deployment.Status.BUILDING, 0),
                    "pending": deployments_by_status.get(Deployment.Status.PENDING, 0),
                    "failed": deployments_by_status.get(Deployment.Status.FAILED, 0),
                    "stopped": deployments_by_status.get(Deployment.Status.STOPPED, 0),
                },
                "global_telemetry": global_metrics,
            }
        )


class DashboardSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = PredictionLog.objects.filter(user=request.user)
        metrics = _compute_metrics(queryset)

        day_ago = timezone.now() - timezone.timedelta(days=1)
        recent_requests_24h = PredictionLog.objects.filter(
            user=request.user,
            created_at__gte=day_ago,
        ).count()

        return Response(
            {
                "metrics": metrics,
                "model_count": Model.objects.filter(owner=request.user).count(),
                "active_api_keys": APIKey.objects.filter(
                    user=request.user, is_active=True
                ).count(),
                "recent_requests_24h": recent_requests_24h,
            }
        )


class DashboardRecentPredictionsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 10))
        except ValueError:
            limit = 10

        limit = max(1, min(limit, 50))

        logs = (
            PredictionLog.objects.filter(user=request.user)
            .select_related("model")
            .order_by("-created_at")[:limit]
        )

        data = [
            {
                "id": str(log.id),
                "uid": str(log.uid),
                "model_id": str(log.model_id),
                "model_name": log.model.name,
                "status": log.status,
                "latency_ms": float(log.latency_ms or 0),
                "cache_hit": log.cache_hit,
                "created_at": log.created_at,
                "error_message": log.error_message,
            }
            for log in logs
        ]
        return Response(data)


class DashboardModelsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        models = list(Model.objects.filter(owner=request.user).order_by("-created_at"))
        items = []

        for model in models:
            model_qs = PredictionLog.objects.filter(user=request.user, model=model)
            metrics = _compute_metrics(model_qs)
            latest_version = model.versions.order_by("-created_at").first()
            last_pred = model_qs.order_by("-created_at").values_list("created_at", flat=True).first()

            latest_deployment = None
            if latest_version:
                latest_deployment = (
                    Deployment.objects.filter(model_version=latest_version)
                    .order_by("-created_at")
                    .first()
                )

            items.append(
                {
                    "model_id": str(model.id),
                    "model_name": model.name,
                    "framework": model.framework,
                    "task_type": model.task_type,
                    "latest_version": latest_version.version if latest_version else None,
                    "latest_version_id": str(latest_version.id) if latest_version else None,
                    "latest_deployment_status": latest_deployment.status if latest_deployment else "NOT_DEPLOYED",
                    "latest_deployment_id": str(latest_deployment.id) if latest_deployment else None,
                    "last_prediction_at": last_pred,
                    **metrics,
                }
            )

        return Response(items)
