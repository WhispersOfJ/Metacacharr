from rest_framework import serializers


class SeerrQuerySerializer(serializers.Serializer):
    status = serializers.CharField(default="pending")
