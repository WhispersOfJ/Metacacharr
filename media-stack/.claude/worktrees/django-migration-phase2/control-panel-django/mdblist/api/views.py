from core.api_base import EnvelopeAPIView
from core.permissions import IsAuthenticatedSessionOnly
from mdblist import services
from mdblist.api.serializers import (
    ImportListRequestSerializer,
    TrackRequestSerializer,
    UntrackRequestSerializer,
)


class ImportListView(EnvelopeAPIView):
    """POST /api/v2/mdblist/import-list.
    Default tier (IsAuthenticatedOrServiceKey): stack-mdblist-import.fish
    calls this unattended via the service key, same documented automation
    exception as the FastAPI-era route."""

    def post(self, request):
        body = ImportListRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = services.import_list(
            data["list_url"], app=data["app"], sonarr_app=data["sonarr_app"], monitored=data["monitored"],
            search=data["search"], limit=data["limit"], radarr_root_folder=data["radarr_root_folder"],
            radarr_quality_profile=data["radarr_quality_profile"], sonarr_root_folder=data["sonarr_root_folder"],
            sonarr_quality_profile=data["sonarr_quality_profile"], dry_run=data["dry_run"],
        )
        message = result.pop("message")
        return self.ok(message, **result)


class HistoryView(EnvelopeAPIView):
    """GET /api/v2/mdblist/history - default tier."""

    def get(self, request):
        result = services.get_history()
        message = result.pop("message")
        return self.ok(message, **result)


class TrackView(EnvelopeAPIView):
    """POST /api/v2/mdblist/track.
    Session-only (no API key) - registering a tracked list is a mutating
    DB-row endpoint with no automation caller, same tier as radarr's
    exclude route."""

    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request):
        body = TrackRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = services.track(
            data["url"], app=data["app"], sonarr_app=data["sonarr_app"], label=data["label"],
            radarr_root_folder=data["radarr_root_folder"], radarr_quality_profile=data["radarr_quality_profile"],
            sonarr_root_folder=data["sonarr_root_folder"], sonarr_quality_profile=data["sonarr_quality_profile"],
        )
        message = result.pop("message")
        return self.ok(message, **result)


class UntrackView(EnvelopeAPIView):
    """POST /api/v2/mdblist/untrack. Session-only - same reasoning as TrackView."""

    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request):
        body = UntrackRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = services.untrack(body.validated_data["url"])
        message = result.pop("message")
        return self.ok(message, **result)


class TrackedView(EnvelopeAPIView):
    """GET /api/v2/mdblist/tracked - default tier."""

    def get(self, request):
        result = services.list_tracked()
        message = result.pop("message")
        return self.ok(message, **result)


class SyncTickView(EnvelopeAPIView):
    """POST /api/v2/mdblist/sync-tick.
    Default tier (IsAuthenticatedOrServiceKey): scripts/mdblist-sync.py
    calls this unattended via the service key, same documented automation
    exception as the FastAPI-era route."""

    def post(self, request):
        result = services.sync_tick()
        message = result.pop("message")
        return self.ok(message, **result)
