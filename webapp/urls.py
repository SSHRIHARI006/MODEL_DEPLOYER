from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("auth/", views.auth_page, name="auth-page"),
    path("dashboard/", views.dashboard_page, name="dashboard-page"),
    path("models/<str:model_id>/", views.model_detail_page, name="model-detail-page"),
]