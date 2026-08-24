from rest_framework import serializers


class HistoryQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(default=20)
