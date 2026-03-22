from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("webapp.urls")),
    path("api/", include("prediction_gateway.urls")),
    path("api/models/", include("model_registry.urls")),
    path("api/auth/", include("authentication.urls")),
    path("api/keys/", include("api_keys.urls")),
]