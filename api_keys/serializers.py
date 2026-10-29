from rest_framework import serializers
from .models import APIKey


class APIKeyCreateSerializer(serializers.Serializer):
    model_id = serializers.CharField()
    name = serializers.CharField(required=False, default="default", max_length=100)


class APIKeyListSerializer(serializers.ModelSerializer):
    """Listing never exposes the key material, only a display prefix (SEC-07)."""

    class Meta:
        model = APIKey
        fields = ["id", "name", "model_id", "key_prefix", "is_active", "created_at"]
