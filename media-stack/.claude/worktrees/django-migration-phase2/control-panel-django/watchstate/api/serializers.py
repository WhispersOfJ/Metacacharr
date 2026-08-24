from rest_framework import serializers


class HistoryQuerySerializer(serializers.Serializer):
    item = serializers.CharField(default="", allow_blank=True)
    limit = serializers.IntegerField(default=20)
