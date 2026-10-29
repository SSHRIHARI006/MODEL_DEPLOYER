from django.urls import path
from .views import (
    ModelUploadAPIView,
    ModelDetailAPIView,
    ModelVersionListCreateAPIView,
    ModelVersionDetailAPIView,
)

urlpatterns = [
    path("upload/", ModelUploadAPIView.as_view(), name="upload-model"),
    path("<str:model_id>/", ModelDetailAPIView.as_view(), name="model-detail"),
    path(
        "<str:model_id>/versions/",
        ModelVersionListCreateAPIView.as_view(),
        name="model-versions",
    ),
    path(
        "<str:model_id>/versions/<str:version>/",
        ModelVersionDetailAPIView.as_view(),
        name="model-version-detail",
    ),
]
