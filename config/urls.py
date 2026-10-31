from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from model_registry.marketplace_views import (
    ExploreAPIView,
    UserProfileAPIView,
    ModelRepoAPIView,
    DashboardSummaryAPIView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # Marketplace endpoints
    path("api/models/explore/", ExploreAPIView.as_view(), name="explore"),
    path(
        "api/users/@<str:username>/",
        UserProfileAPIView.as_view(),
        name="user-profile",
    ),
    path(
        "api/models/@<str:username>/<str:model_name>/",
        ModelRepoAPIView.as_view(),
        name="model-repo",
    ),
    path(
        "api/dashboard/summary/",
        DashboardSummaryAPIView.as_view(),
        name="dashboard-summary",
    ),
    # Legacy and standard endpoints
    path("api/", include("prediction_gateway.urls")),
    path("api/deployments/", include("deployments.urls")),
    path("api/models/", include("model_registry.urls")),
    path("api/auth/", include("authentication.urls")),
    path("api/keys/", include("api_keys.urls")),
    path("api/metrics/", include("monitoring.urls")),
    path("api/", include("billing.urls")),
]

# The API container is also the source for Django admin/static assets. The
# reverse proxy keeps this path private to the application host in production.
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
