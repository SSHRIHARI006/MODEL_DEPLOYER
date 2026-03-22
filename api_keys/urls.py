from django.urls import path
from .views import APIKeyListCreateAPIView, APIKeyDeactivateAPIView

urlpatterns = [
    path("", APIKeyListCreateAPIView.as_view(), name="api-key-list-create"),
    path("<uuid:key_id>/deactivate/", APIKeyDeactivateAPIView.as_view(), name="api-key-deactivate"),
]