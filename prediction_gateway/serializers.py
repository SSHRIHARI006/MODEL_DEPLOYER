from rest_framework import serializers


class PredictRequestSerializer(serializers.Serializer):
    payload = serializers.JSONField()

    def validate_payload(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("payload must be an object")
        return value