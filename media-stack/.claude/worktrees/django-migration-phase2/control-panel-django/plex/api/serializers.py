from rest_framework import serializers


class LibraryQuerySerializer(serializers.Serializer):
    """Optional `library` query param for empty-trash/analyze - matched
    case-insensitively against a Plex library title in services.py. Absent
    (default=None) means "every library", matching the FastAPI-era
    `library: str | None = None` query param."""

    library = serializers.CharField(required=False, allow_blank=False, default=None)


class DuplicatesQuerySerializer(serializers.Serializer):
    min_gb = serializers.FloatField(default=5.0)


class RecentlyAddedQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(default=15)
