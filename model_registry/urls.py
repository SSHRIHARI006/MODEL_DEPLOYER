from django.urls import path
from .views import ModelUploadAPIView

urlpatterns = [
    path("upload/", ModelUploadAPIView.as_view(), name="upload-model"),
]