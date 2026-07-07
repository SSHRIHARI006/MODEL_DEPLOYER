from django.urls import path
from .views import PredictAPIView, UniversalInferenceAPIView

urlpatterns = [
    path("predict/<str:model_id>/", PredictAPIView.as_view(), name="predict"),
    path("v1/inference/@<str:username>/<str:model_name>/", UniversalInferenceAPIView.as_view(), name="universal-predict"),
]
