from django.urls import path
from .views import PredictAPIView

urlpatterns = [
    path("predict/<str:model_id>/", PredictAPIView.as_view(), name="predict"),
]