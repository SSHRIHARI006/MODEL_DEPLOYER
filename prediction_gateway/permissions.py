from rest_framework.permissions import BasePermission
from api_keys.models import APIKey


class HasValidModelAPIKey(BasePermission):
    message = "Invalid or missing API key"

    def has_permission(self, request, view):
        model_id = view.kwargs.get("model_id")
        api_key = request.headers.get("X-API-Key")

        if not model_id or not api_key:
            return False

        try:
            key_obj = APIKey.objects.get(
                key=api_key,
                is_active=True,
                model_id=model_id,
            )
        except APIKey.DoesNotExist:
            return False

        if key_obj.user_id != request.user.id:
            return False

        request.api_key_obj = key_obj
        return True