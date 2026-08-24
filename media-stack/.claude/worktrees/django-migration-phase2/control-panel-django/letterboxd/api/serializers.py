from rest_framework import serializers


class AddRequestSerializer(serializers.Serializer):
    """Mirrors the FastAPI-era LetterboxdAddRequest Pydantic model - field
    names stay snake_case (not camelCased), same convention as mdblist."""

    url = serializers.CharField()
    app = serializers.CharField(default="radarr")
    monitored = serializers.BooleanField(default=True)
    search = serializers.BooleanField(default=True)
    root_folder = serializers.CharField(required=False, allow_null=True, default=None)
    quality_profile = serializers.CharField(required=False, allow_null=True, default=None)
    dry_run = serializers.BooleanField(default=False)


class ListAddRequestSerializer(serializers.Serializer):
    """Mirrors the FastAPI-era LetterboxdListAddRequest Pydantic model."""

    url = serializers.CharField()
    app = serializers.CharField(default="radarr")
    monitored = serializers.BooleanField(default=True)
    search = serializers.BooleanField(default=True)
    root_folder = serializers.CharField(required=False, allow_null=True, default=None)
    quality_profile = serializers.CharField(required=False, allow_null=True, default=None)
    limit = serializers.IntegerField(required=False, allow_null=True, default=None)
    dry_run = serializers.BooleanField(default=False)
    rating_quality_map = serializers.DictField(
        child=serializers.CharField(), required=False, allow_null=True, default=None,
    )
    tags_as_radarr_tags = serializers.BooleanField(default=False)
    sonarr_crossover = serializers.BooleanField(default=False)
    sonarr_app = serializers.CharField(default="sonarr")


class TrackRequestSerializer(serializers.Serializer):
    """Mirrors the FastAPI-era TrackRequest Pydantic model."""

    url = serializers.CharField()
    app = serializers.CharField(default="radarr")
    label = serializers.CharField(required=False, allow_null=True, default=None)
    root_folder = serializers.CharField(required=False, allow_null=True, default=None)
    quality_profile = serializers.CharField(required=False, allow_null=True, default=None)
    rating_quality_map = serializers.DictField(
        child=serializers.CharField(), required=False, allow_null=True, default=None,
    )
    tags_as_radarr_tags = serializers.BooleanField(default=False)
    sonarr_app = serializers.CharField(default="sonarr")


class UntrackRequestSerializer(serializers.Serializer):
    """Mirrors the FastAPI-era UntrackRequest Pydantic model."""

    url = serializers.CharField()
