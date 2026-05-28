from rest_framework import serializers


class PredictRequestSerializer(serializers.Serializer):
    instances = serializers.ListField(child=serializers.DictField(), allow_empty=False)
