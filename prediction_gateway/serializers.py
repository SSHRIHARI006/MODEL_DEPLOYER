from rest_framework import serializers


class PredictRequestSerializer(serializers.Serializer):
    instances = serializers.ListField(allow_empty=False)
