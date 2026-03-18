from django.urls import path
from . import views

urlpatterns = [
    path("predict/<str:model_id>/", views.predict, name="predict"),
]