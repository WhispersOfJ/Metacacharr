from rest_framework import serializers


class ImportListRequestSerializer(serializers.Serializer):
    """Mirrors the FastAPI-era MDBListImportRequest Pydantic model - field
    names stay snake_case (not camelCased) since that's what
    fish-functions/stack-mdblist-import.fish already sends."""

    list_url = serializers.CharField()
    app = serializers.CharField(default="radarr")
    sonarr_app = serializers.CharField(default="sonarr")
    monitored = serializers.BooleanField(default=True)
    search = serializers.BooleanField(default=True)
    limit = serializers.IntegerField(required=False, allow_null=True, default=None)
    radarr_root_folder = serializers.CharField(required=False, allow_null=True, default=None)
    radarr_quality_profile = serializers.CharField(required=False, allow_null=True, default=None)
    sonarr_root_folder = serializers.CharField(required=False, allow_null=True, default=None)
    sonarr_quality_profile = serializers.CharField(required=False, allow_null=True, default=None)
    dry_run = serializers.BooleanField(default=False)


class TrackRequestSerializer(serializers.Serializer):
    """Mirrors the FastAPI-era TrackRequest Pydantic model."""

    url = serializers.CharField()
    app = serializers.CharField(default="radarr")
    sonarr_app = serializers.CharField(default="sonarr")
    label = serializers.CharField(required=False, allow_null=True, default=None)
    radarr_root_folder = serializers.CharField(required=False, allow_null=True, default=None)
    radarr_quality_profile = serializers.CharField(required=False, allow_null=True, default=None)
    sonarr_root_folder = serializers.CharField(required=False, allow_null=True, default=None)
    sonarr_quality_profile = serializers.CharField(required=False, allow_null=True, default=None)


class UntrackRequestSerializer(serializers.Serializer):
    """Mirrors the FastAPI-era UntrackRequest Pydantic model."""

    url = serializers.CharField()
