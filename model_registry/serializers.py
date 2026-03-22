from rest_framework import serializers


class ModelUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        if not value.name.endswith(".zip"):
            raise serializers.ValidationError("Only .zip files allowed")
        return value