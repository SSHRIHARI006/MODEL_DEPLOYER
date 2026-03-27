from django.urls import path

from .views import DeploymentCreateAPIView, DeploymentDetailAPIView

urlpatterns = [
    path("", DeploymentCreateAPIView.as_view(), name="deployment-create"),
    path("<uuid:deployment_id>/", DeploymentDetailAPIView.as_view(), name="deployment-detail"),
]
