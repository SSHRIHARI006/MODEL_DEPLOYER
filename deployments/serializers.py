from rest_framework import serializers

from model_registry.models import ModelVersion

from .models import Deployment


class DeploymentCreateSerializer(serializers.Serializer):
    model_version_id = serializers.UUIDField()

    def validate_model_version_id(self, value):
        user = self.context["request"].user
        try:
            model_version = ModelVersion.objects.select_related("model").get(id=value)
        except ModelVersion.DoesNotExist as exc:
            raise serializers.ValidationError("Model version not found") from exc

        if model_version.model.owner_id != user.id:
            raise serializers.ValidationError("You can deploy only your own model versions")

        return value


class DeploymentSerializer(serializers.ModelSerializer):
    model_version_id = serializers.UUIDField(source="model_version.id", read_only=True)

    class Meta:
        model = Deployment
        fields = [
            "id",
            "model_version_id",
            "status",
            "runtime_type",
            "image_name",
            "container_name",
            "container_id",
            "internal_url",
            "last_error",
            "created_at",
            "updated_at",
            "started_at",
            "stopped_at",
        ]
