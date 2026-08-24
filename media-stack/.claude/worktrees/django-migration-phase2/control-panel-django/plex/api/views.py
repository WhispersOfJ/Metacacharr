"""Plex diagnostics/maintenance routes, ported from
control-panel/services/plex/router.py. Every view is the default
EnvelopeAPIView tier (IsAuthenticatedOrServiceKey) - matches the
FastAPI-era current_user_or_service dependency used on every route in the
source file (no session-only routes in this app)."""
from core.api_base import EnvelopeAPIView
from plex import services
from plex.api.serializers import DuplicatesQuerySerializer, LibraryQuerySerializer, RecentlyAddedQuerySerializer


class ScanView(EnvelopeAPIView):
    """POST /api/v2/plex/scan."""

    def post(self, request):
        result = services.scan()
        return self.ok(result["message"])


class LibrariesView(EnvelopeAPIView):
    """GET /api/v2/plex/libraries."""

    def get(self, request):
        result = services.list_libraries()
        message = result.pop("message")
        return self.ok(message, **result)


class EmptyTrashView(EnvelopeAPIView):
    """POST /api/v2/plex/empty-trash?library=..."""

    def post(self, request):
        query = LibraryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.empty_trash(query.validated_data.get("library"))
        return self.ok(result["message"])


class AnalyzeView(EnvelopeAPIView):
    """POST /api/v2/plex/analyze?library=..."""

    def post(self, request):
        query = LibraryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.analyze(query.validated_data.get("library"))
        return self.ok(result["message"])


class OptimizeDbView(EnvelopeAPIView):
    """POST /api/v2/plex/optimize-db."""

    def post(self, request):
        result = services.optimize_db()
        return self.ok(result["message"])


class CleanBundlesView(EnvelopeAPIView):
    """POST /api/v2/plex/clean-bundles."""

    def post(self, request):
        result = services.clean_bundles()
        return self.ok(result["message"])


class ButlerTaskView(EnvelopeAPIView):
    """POST /api/v2/plex/butler/<task> - `task` is this stack's own
    kebab-case alias (see plex.services.PLEX_BUTLER_TASKS)."""

    def post(self, request, task):
        result = services.butler_task(task)
        return self.ok(result["message"])


class UpdatesView(EnvelopeAPIView):
    """GET /api/v2/plex/updates."""

    def get(self, request):
        result = services.get_updates()
        message = result.pop("message")
        return self.ok(message, **result)


class ScanHealthView(EnvelopeAPIView):
    """GET /api/v2/plex/scan-health."""

    def get(self, request):
        result = services.scan_health()
        message = result.pop("message")
        return self.ok(message, **result)


class DuplicatesView(EnvelopeAPIView):
    """GET /api/v2/plex/duplicates?min_gb=..."""

    def get(self, request):
        query = DuplicatesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.duplicates(query.validated_data["min_gb"])
        message = result.pop("message")
        return self.ok(message, **result)


class TmdbMissingView(EnvelopeAPIView):
    """GET /api/v2/plex/tmdb-missing."""

    def get(self, request):
        result = services.tmdb_missing()
        message = result.pop("message")
        return self.ok(message, **result)


class SessionsView(EnvelopeAPIView):
    """GET /api/v2/plex/sessions."""

    def get(self, request):
        result = services.sessions()
        message = result.pop("message")
        return self.ok(message, **result)


class RecentlyAddedView(EnvelopeAPIView):
    """GET /api/v2/plex/recently-added?limit=..."""

    def get(self, request):
        query = RecentlyAddedQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.recently_added(query.validated_data["limit"])
        message = result.pop("message")
        return self.ok(message, **result)
