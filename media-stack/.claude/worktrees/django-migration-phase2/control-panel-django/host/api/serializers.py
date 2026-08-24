from rest_framework import serializers


class SettingsPatchSerializer(serializers.Serializer):
    """Matches the FastAPI-era SettingsPatch(BaseModel) - every field
    optional; only the ones present in the request are applied."""

    theme = serializers.CharField(required=False, allow_null=True)
    failed_pending_storm_threshold = serializers.IntegerField(required=False, allow_null=True)
    loop_review_profile_threshold = serializers.IntegerField(required=False, allow_null=True)


class RestartQuerySerializer(serializers.Serializer):
    """activated=true is required to restart Plex (by design, matching the
    FastAPI-era route) - defaults to False so a plain restart click can't
    silently pass."""

    activated = serializers.BooleanField(default=False)


class PruneRequestSerializer(serializers.Serializer):
    """confirm defaults to False, so an omitted field is treated as an
    explicit no (matching the FastAPI-era PruneRequest)."""

    confirm = serializers.BooleanField(default=False)


class TopQuerySerializer(serializers.Serializer):
    by = serializers.CharField(default="cpu")
    limit = serializers.IntegerField(default=10)


class LogsStreamQuerySerializer(serializers.Serializer):
    tail = serializers.IntegerField(default=100)
