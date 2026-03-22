from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from model_registry.models import Model
from .models import APIKey
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