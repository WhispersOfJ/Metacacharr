from rest_framework import serializers

SOURCE_CHOICES = ["tmdb", "fanart", "tvdb", "omdb", "tvmaze"]


class SyncRequestSerializer(serializers.Serializer):
    library = serializers.CharField()
    dry_run = serializers.BooleanField(default=False)
    source = serializers.ChoiceField(choices=SOURCE_CHOICES, default="tmdb")


class ReviewRequestSerializer(serializers.Serializer):
    library = serializers.CharField()
    source = serializers.ChoiceField(choices=SOURCE_CHOICES, default="fanart")


class ApplyRequestSerializer(serializers.Serializer):
    rating_key = serializers.CharField()
    url = serializers.CharField()


class ScanRequestSerializer(serializers.Serializer):
    library = serializers.CharField()


class GalleryQuerySerializer(serializers.Serializer):
    library = serializers.CharField()
    offset = serializers.IntegerField(default=0, min_value=0)
    limit = serializers.IntegerField(default=60, min_value=1, max_value=200)
