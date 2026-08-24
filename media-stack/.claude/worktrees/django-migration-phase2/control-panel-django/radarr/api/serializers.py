from rest_framework import serializers


class ExcludeRequestSerializer(serializers.Serializer):
    """Request body schema for movie exclusion endpoint."""

    movieId = serializers.IntegerField()
