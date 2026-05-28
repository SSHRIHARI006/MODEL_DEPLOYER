from django.urls import path
from .views import ModelUploadAPIView, ModelDetailAPIView

urlpatterns = [
    path("upload/", ModelUploadAPIView.as_view(), name="upload-model"),
    path("<str:model_id>/", ModelDetailAPIView.as_view(), name="model-detail"),
]
