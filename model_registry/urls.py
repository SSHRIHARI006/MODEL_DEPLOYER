from django.urls import path
from . import views

urlpatterns = [
    path("upload/", views.upload_model, name="upload_model"),
]