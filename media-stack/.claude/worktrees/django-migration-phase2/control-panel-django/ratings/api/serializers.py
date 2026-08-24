from rest_framework import serializers


class RatingQuerySerializer(serializers.Serializer):
    imdb_id = serializers.CharField()
