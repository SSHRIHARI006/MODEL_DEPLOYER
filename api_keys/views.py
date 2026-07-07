from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from model_registry.models import Model
from .models import APIKey, UniversalAPIKey
from .serializers import APIKeyCreateSerializer, APIKeyListSerializer


class APIKeyListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        keys = APIKey.objects.filter(user=request.user).order_by("-created_at")
        return Response(APIKeyListSerializer(keys, many=True).data)

    def post(self, request):
        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        model = get_object_or_404(
            Model,
            id=serializer.validated_data["model_id"],
            owner=request.user,
        )

        key = APIKey.objects.create(
            user=request.user,
            model=model,
            name=serializer.validated_data["name"],
        )

        return Response(
            {
                "id": str(key.id),
                "name": key.name,
                "model_id": key.model_id,
                "key": key.key,
                "is_active": key.is_active,
                "created_at": key.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class APIKeyDeactivateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, key_id):
        key = get_object_or_404(APIKey, id=key_id, user=request.user)
        key.is_active = False
        key.save(update_fields=["is_active"])
        return Response({"message": "API key deactivated"})


# ---------------------------------------------------------------------------
# Universal API Key endpoints
# ---------------------------------------------------------------------------


class UniversalKeyListCreateAPIView(APIView):
    """List and create user-level universal API keys."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        keys = UniversalAPIKey.objects.filter(user=request.user).order_by("-created_at")
        data = [
            {
                "id": str(k.id),
                "name": k.name,
                "prefix": k.prefix,
                "is_active": k.is_active,
                "created_at": k.created_at,
                "last_used_at": k.last_used_at,
            }
            for k in keys
        ]
        return Response(data)

    def post(self, request):
        name = request.data.get("name", "default")
        raw_key, prefix, hashed = UniversalAPIKey.generate()

        key_obj = UniversalAPIKey.objects.create(
            user=request.user,
            name=name,
            prefix=prefix,
            hashed_key=hashed,
        )

        return Response(
            {
                "id": str(key_obj.id),
                "name": key_obj.name,
                "prefix": prefix,
                "key": raw_key,  # shown only once
                "created_at": key_obj.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class UniversalKeyDeleteAPIView(APIView):
    """Revoke a universal API key."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, key_id):
        key = get_object_or_404(UniversalAPIKey, id=key_id, user=request.user)
        key.is_active = False
        key.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)

