from core.api_base import EnvelopeAPIView
from core.permissions import IsAuthenticatedSessionOnly
from letterboxd import services
from letterboxd.api.serializers import (
    AddRequestSerializer,
    ListAddRequestSerializer,
    TrackRequestSerializer,
    UntrackRequestSerializer,
)


class AddView(EnvelopeAPIView):
    """POST /api/v2/letterboxd/add.
    Default tier (IsAuthenticatedOrServiceKey): stack-letterboxd-radarr.fish
    calls this unattended via the service key, same documented automation
    exception as the FastAPI-era route."""

    def post(self, request):
        body = AddRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = services.add_from_url(
            data["url"], app=data["app"], monitored=data["monitored"], search=data["search"],
            root_folder=data["root_folder"], quality_profile=data["quality_profile"], dry_run=data["dry_run"],
        )
        message = result.pop("message")
        return self.ok(message, **result)


class AddFromListView(EnvelopeAPIView):
    """POST /api/v2/letterboxd/add-from-list.
    Default tier: stack-letterboxd-radarr-list.fish calls this unattended
    via the service key, same documented automation exception as the
    FastAPI-era route."""

    def post(self, request):
        body = ListAddRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = services.add_from_list(
            data["url"], app=data["app"], monitored=data["monitored"], search=data["search"],
            root_folder=data["root_folder"], quality_profile=data["quality_profile"], limit=data["limit"],
            dry_run=data["dry_run"], rating_quality_map=data["rating_quality_map"],
            tags_as_radarr_tags=data["tags_as_radarr_tags"], sonarr_crossover=data["sonarr_crossover"],
            sonarr_app=data["sonarr_app"],
        )
        message = result.pop("message")
        return self.ok(message, **result)


class HistoryView(EnvelopeAPIView):
    """GET /api/v2/letterboxd/history - default tier."""

    def get(self, request):
        result = services.get_history()
        message = result.pop("message")
        return self.ok(message, **result)


class TrackView(EnvelopeAPIView):
    """POST /api/v2/letterboxd/track.
    Session-only (no API key) - registering a tracked list is a mutating
    DB-row endpoint with no automation caller, same tier as mdblist's
    track route (and the FastAPI-era current_user, not
    current_user_or_service, dependency on letterboxd_track)."""

    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request):
        body = TrackRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = services.track(
            data["url"], app=data["app"], label=data["label"], root_folder=data["root_folder"],
            quality_profile=data["quality_profile"], rating_quality_map=data["rating_quality_map"],
            tags_as_radarr_tags=data["tags_as_radarr_tags"], sonarr_app=data["sonarr_app"],
        )
        message = result.pop("message")
        return self.ok(message, **result)


class UntrackView(EnvelopeAPIView):
    """POST /api/v2/letterboxd/untrack. Session-only - same reasoning as
    TrackView (FastAPI-era letterboxd_untrack also used current_user)."""

    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request):
        body = UntrackRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = services.untrack(body.validated_data["url"])
        message = result.pop("message")
        return self.ok(message, **result)


class TrackedView(EnvelopeAPIView):
    """GET /api/v2/letterboxd/tracked - default tier."""

    def get(self, request):
        result = services.list_tracked()
        message = result.pop("message")
        return self.ok(message, **result)


class SyncTickView(EnvelopeAPIView):
    """POST /api/v2/letterboxd/sync-tick.
    Default tier: scripts/letterboxd-sync.py calls this unattended via the
    service key, same documented automation exception as the FastAPI-era
    route."""

    def post(self, request):
        result = services.sync_tick()
        message = result.pop("message")
        return self.ok(message, **result)
