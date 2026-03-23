from django.urls import path

from .views import (
    DashboardModelsAPIView,
    DashboardRecentPredictionsAPIView,
    DashboardSummaryAPIView,
    HealthAPIView,
    MetricsOverviewAPIView,
    ModelMetricsAPIView,
)

urlpatterns = [
    path("health/", HealthAPIView.as_view(), name="health"),
    path("overview/", MetricsOverviewAPIView.as_view(), name="metrics-overview"),
    path("models/<str:model_id>/", ModelMetricsAPIView.as_view(), name="metrics-by-model"),
    path("dashboard/summary/", DashboardSummaryAPIView.as_view(), name="dashboard-summary"),
    path("dashboard/recent-predictions/", DashboardRecentPredictionsAPIView.as_view(), name="dashboard-recent-predictions"),
    path("dashboard/models/", DashboardModelsAPIView.as_view(), name="dashboard-models"),
]
