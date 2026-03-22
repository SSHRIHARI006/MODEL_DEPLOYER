from rest_framework import serializers
from .models import APIKey


class APIKeyCreateSerializer(serializers.Serializer):
    model_id = serializers.CharField()
    name = serializers.CharField(required=False, default="default", max_length=100)


class APIKeyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["id", "name", "model_id", "is_active", "created_at"]