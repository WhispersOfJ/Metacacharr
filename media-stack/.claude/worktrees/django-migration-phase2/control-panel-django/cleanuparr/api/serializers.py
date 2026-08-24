from rest_framework import serializers


class StrikesQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(default=15)
