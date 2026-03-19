from django.urls import path
from .views import predict

urlpatterns = [
    path("predict/<str:model_id>/", predict),
]