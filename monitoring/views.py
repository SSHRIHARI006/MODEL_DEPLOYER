from collections import defaultdict
from statistics import mean

from django.db import connections
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.models import APIKey
from model_registry.models import Model
from prediction_gateway.models import PredictionLog


def _compute_metrics(logs):
    total_requests = len(logs)
    success_count = sum(1 for log in logs if log.status == "SUCCESS")
    error_count = sum(1 for log in logs if log.status == "ERROR")

    if total_requests == 0:
        return {
            "total_requests": 0,
            "success_count": 0,
            "error_count": 0,
            "success_rate": 0.0,
            "avg_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
        }

    latencies = sorted(float(log.latency_ms or 0) for log in logs)
    avg_latency_ms = round(mean(latencies), 3)
    p95_index = max(0, min(len(latencies) - 1, int(0.95 * len(latencies)) - 1))
    p95_latency_ms = round(latencies[p95_index], 3)

    return {
        "total_requests": total_requests,
        "success_count": success_count,
        "error_count": error_count,
        "success_rate": round((success_count / total_requests) * 100, 2),
        "avg_latency_ms": avg_latency_ms,
        "p95_latency_ms": p95_latency_ms,
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


class MetricsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logs = list(PredictionLog.objects.filter(user=request.user).order_by("-created_at"))
        return Response(_compute_metrics(logs))


class ModelMetricsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, model_id):
        model = get_object_or_404(Model, id=model_id, owner=request.user)
        logs = list(
            PredictionLog.objects.filter(user=request.user, model=model).order_by("-created_at")
        )
        data = _compute_metrics(logs)
        data.update(
            {
                "model_id": str(model.id),
                "model_name": model.name,
            }
        )
        return Response(data)


class DashboardSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logs = list(PredictionLog.objects.filter(user=request.user).order_by("-created_at"))
        metrics = _compute_metrics(logs)

        day_ago = timezone.now() - timezone.timedelta(days=1)
        recent_requests_24h = PredictionLog.objects.filter(
            user=request.user,
            created_at__gte=day_ago,
        ).count()

        return Response(
            {
                "metrics": metrics,
                "model_count": Model.objects.filter(owner=request.user).count(),
                "active_api_keys": APIKey.objects.filter(user=request.user, is_active=True).count(),
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
                "uid": log.uid,
                "model_id": str(log.model_id),
                "model_name": log.model.name,
                "status": log.status,
                "latency_ms": float(log.latency_ms or 0),
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
        model_ids = [model.id for model in models]

        logs = list(
            PredictionLog.objects.filter(user=request.user, model_id__in=model_ids).order_by("-created_at")
        )

        logs_by_model = defaultdict(list)
        for log in logs:
            logs_by_model[str(log.model_id)].append(log)

        items = []
        for model in models:
            model_logs = logs_by_model.get(str(model.id), [])
            metrics = _compute_metrics(model_logs)
            latest_version = model.versions.order_by("-created_at").first()
            last_prediction_at = model_logs[0].created_at if model_logs else None

            items.append(
                {
                    "model_id": str(model.id),
                    "model_name": model.name,
                    "framework": model.framework,
                    "task_type": model.task_type,
                    "latest_version": latest_version.version if latest_version else None,
                    "last_prediction_at": last_prediction_at,
                    **metrics,
                }
            )

        return Response(items)
