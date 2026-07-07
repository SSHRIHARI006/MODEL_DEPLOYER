from django.urls import path
from .views import (
    APIKeyListCreateAPIView,
    APIKeyDeactivateAPIView,
    UniversalKeyListCreateAPIView,
    UniversalKeyDeleteAPIView,
)

urlpatterns = [
    path("", APIKeyListCreateAPIView.as_view(), name="api-key-list-create"),
    path(
        "<uuid:key_id>/deactivate/",
        APIKeyDeactivateAPIView.as_view(),
        name="api-key-deactivate",
    ),
    # Universal API keys
    path(
        "universal/",
        UniversalKeyListCreateAPIView.as_view(),
        name="universal-key-list-create",
    ),
    path(
        "universal/<uuid:key_id>/",
        UniversalKeyDeleteAPIView.as_view(),
        name="universal-key-delete",
    ),
]
