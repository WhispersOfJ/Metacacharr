from rest_framework import serializers
from rest_framework.fields import empty


class RequiredBooleanField(serializers.BooleanField):
    """BooleanField with default_empty_html=empty instead of False.

    DRF's stock BooleanField.default_empty_html is False (the HTML-checkbox
    convention: an unchecked box is an absent field), which leaks into
    query-param serializers: request.query_params is a QueryDict, so a
    missing ?enabled= would silently validate as False instead of erroring.
    The FastAPI-era route signature was `enabled: bool` (required, no
    default) - this restores that: an absent value is a 400, an explicit
    ?enabled=false is False."""

    default_empty_html = empty


class UnmonitorRequest(serializers.Serializer):
    """Matches the FastAPI-era UnmonitorRequest(BaseModel): ids is required."""

    ids = serializers.ListField(child=serializers.IntegerField())


class ManualImportFile(serializers.Serializer):
    """Matches the FastAPI-era ManualImportFile(BaseModel) - path and
    quality/languages required, everything else optional; the service drops
    None values before sending (exclude_none=True in the FastAPI source)."""

    path = serializers.CharField()
    folderName = serializers.CharField(required=False, allow_null=True)
    quality = serializers.DictField()
    languages = serializers.ListField(child=serializers.DictField())
    releaseGroup = serializers.CharField(required=False, allow_null=True)
    downloadId = serializers.CharField(required=False, allow_null=True)
    movieId = serializers.IntegerField(required=False, allow_null=True)
    seriesId = serializers.IntegerField(required=False, allow_null=True)
    episodeIds = serializers.ListField(child=serializers.IntegerField(), required=False, allow_null=True)
    artistId = serializers.IntegerField(required=False, allow_null=True)
    albumId = serializers.IntegerField(required=False, allow_null=True)
    trackIds = serializers.ListField(child=serializers.IntegerField(), required=False, allow_null=True)
    authorId = serializers.IntegerField(required=False, allow_null=True)
    bookId = serializers.IntegerField(required=False, allow_null=True)


class ImportListAddRequest(serializers.Serializer):
    """Matches the FastAPI-era ImportListAddRequest(BaseModel)."""

    implementation = serializers.CharField()
    name = serializers.CharField()
    fields = serializers.DictField(required=False, default=dict)
    search_on_add = serializers.BooleanField(default=True)
    # default=None (not just allow_null) so the key is always present in
    # validated_data - matches the FastAPI-era `monitor: str | None = None`
    # default, which the service's .get("monitor") or "..." branch reads.
    monitor = serializers.CharField(required=False, allow_null=True, default=None)
    minimum_availability = serializers.CharField(default="released")


class SearchToggleQuerySerializer(serializers.Serializer):
    enabled = RequiredBooleanField()


class LoopCandidatesQuerySerializer(serializers.Serializer):
    hours = serializers.FloatField(default=6.0)


class BlocklistQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(default=50)


class LogsQuerySerializer(serializers.Serializer):
    lines = serializers.IntegerField(default=100)


class RecentlyAddedQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(default=10)


class CutoffUnmetQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(default=20)
