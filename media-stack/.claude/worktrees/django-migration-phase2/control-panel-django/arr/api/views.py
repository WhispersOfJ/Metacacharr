"""Generic Radarr/Sonarr routes that dispatch on {app_name}. Ported from
control-panel/services/arr/router.py.

Every view is the default EnvelopeAPIView tier (IsAuthenticatedOrServiceKey)
- matches the FastAPI-era current_user_or_service dependency used on all 27
routes, including the mutating ones: this is the app with the most
unattended-automation callers (stack-queue-autofix.fish's 5-minute cron loop,
the stack-cli-arr-fleet skill's commands), all calling via __stack_api's
service key with no interactive session. No route here is tightened to
session-only - a regression would silently break that cron loop.
"""
from core.api_base import EnvelopeAPIView
from arr import services
from arr.api.serializers import (
    BlocklistQuerySerializer,
    CutoffUnmetQuerySerializer,
    ImportListAddRequest,
    LogsQuerySerializer,
    LoopCandidatesQuerySerializer,
    ManualImportFile,
    RecentlyAddedQuerySerializer,
    SearchToggleQuerySerializer,
    UnmonitorRequest,
)


class RssSyncView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/rss-sync"""

    def post(self, request, app_name):
        return self.ok(services.rss_sync(app_name))


class SearchMissingView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/search-missing"""

    def post(self, request, app_name):
        return self.ok(services.search_missing(app_name))


class SearchStatusView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/search-status"""

    def get(self, request, app_name):
        result = services.search_status(app_name)
        return self.ok("Search status", **result)


class SearchToggleView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/search-toggle?enabled=true|false"""

    def post(self, request, app_name):
        query = SearchToggleQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        message = services.search_toggle(app_name, query.validated_data["enabled"])
        return self.ok(message)


class CommandBacklogView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/command-backlog"""

    def get(self, request, app_name):
        result = services.command_backlog(app_name)
        message = result.pop("message")
        return self.ok(message, **result)


class UnstickView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/unstick"""

    def post(self, request, app_name):
        result = services.unstick(app_name)
        message = result.pop("message")
        return self.ok(message, **result)


class UnstickImportingView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/unstick-importing"""

    def post(self, request, app_name):
        result = services.unstick_importing(app_name)
        message = result.pop("message")
        return self.ok(message, **result)


class ImportStarvationView(EnvelopeAPIView):
    """GET /api/v2/arr/import-starvation"""

    def get(self, request):
        result = services.import_starvation_status()
        message = result.pop("message")
        return self.ok(message, **result)


class QueueAutofixView(EnvelopeAPIView):
    """POST /api/v2/arr/queue-autofix"""

    def post(self, request):
        result = services.queue_autofix()
        message = result.pop("message")
        return self.ok(message, **result)


class LoopCandidatesView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/loop-candidates?hours=..."""

    def get(self, request, app_name):
        query = LoopCandidatesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.loop_candidates(app_name, query.validated_data["hours"])
        message = result.pop("message")
        return self.ok(message, **result)


class UnmonitorView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/unmonitor"""

    def post(self, request, app_name):
        body = UnmonitorRequest(data=request.data)
        body.is_valid(raise_exception=True)
        result = services.unmonitor(app_name, body.validated_data["ids"])
        message = result.pop("message")
        return self.ok(message, **result)


class ManualImportView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/manual-import - candidate files.
    POST /api/v2/arr/<app_name>/manual-import - execute one import.
    One view handles both methods on the same URL, like host's
    SettingsView."""

    def get(self, request, app_name):
        items = services.manual_import_candidates(app_name)
        return self.ok(f"{len(items)} manual-import candidate(s).", items=items)

    def post(self, request, app_name):
        body = ManualImportFile(data=request.data)
        body.is_valid(raise_exception=True)
        payload = {k: v for k, v in body.validated_data.items() if v is not None}
        message = services.manual_import_execute(app_name, payload)
        return self.ok(message)


class ManualImportAllView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/manual-import-all"""

    def post(self, request, app_name):
        message = services.manual_import_all(app_name)
        return self.ok(message)


class MissingAiredView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/missing-aired"""

    def get(self, request, app_name):
        items = services.missing_aired(app_name)
        return self.ok(f"{len(items)} aired-but-missing item(s).", items=items)


class BlocklistView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/blocklist?limit=..."""

    def get(self, request, app_name):
        query = BlocklistQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.blocklist(app_name, query.validated_data["limit"])
        message = result.pop("message")
        return self.ok(message, **result)


class BlocklistClearView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/blocklist/clear"""

    def post(self, request, app_name):
        result = services.blocklist_clear(app_name)
        message = result.pop("message")
        return self.ok(message, **result)


class BacklogStatusView(EnvelopeAPIView):
    """GET /api/v2/arr/backlog-status"""

    def get(self, request):
        result = services.backlog_status()
        message = result.pop("message")
        return self.ok(message, **result)


class LogsView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/logs?lines=..."""

    def get(self, request, app_name):
        query = LogsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        log = services.logs(app_name, query.validated_data["lines"])
        return self.ok(f"Last {query.validated_data['lines']} line(s) from {app_name}.", log=log)


class CommandQueueSummaryView(EnvelopeAPIView):
    """GET /api/v2/arr/command-queue-summary"""

    def get(self, request):
        result = services.command_queue_summary()
        message = result.pop("message")
        return self.ok(message, **result)


class RecentlyAddedView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/recently-added?limit=..."""

    def get(self, request, app_name):
        query = RecentlyAddedQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.recently_added(app_name, query.validated_data["limit"])
        message = result.pop("message")
        return self.ok(message, **result)


class QueueErrorsView(EnvelopeAPIView):
    """GET /api/v2/arr/queue-errors"""

    def get(self, request):
        result = services.queue_errors()
        message = result.pop("message")
        return self.ok(message, **result)


class CutoffUnmetView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/cutoff-unmet?limit=..."""

    def get(self, request, app_name):
        query = CutoffUnmetQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.cutoff_unmet(app_name, query.validated_data["limit"])
        message = result.pop("message")
        return self.ok(message, **result)


class ImportListsView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/import-lists"""

    def get(self, request, app_name):
        result = services.import_lists(app_name)
        message = result.pop("message")
        return self.ok(message, **result)


class ImportListImplementationsView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/import-list/implementations"""

    def get(self, request, app_name):
        result = services.import_list_implementations(app_name)
        message = result.pop("message")
        return self.ok(message, **result)


class ImportListAddView(EnvelopeAPIView):
    """POST /api/v2/arr/<app_name>/import-list/add"""

    def post(self, request, app_name):
        body = ImportListAddRequest(data=request.data)
        body.is_valid(raise_exception=True)
        payload = body.validated_data
        result = services.import_list_add(app_name, payload)
        message = result.pop("message")
        return self.ok(message, **result)


class CustomformatSnapshotView(EnvelopeAPIView):
    """GET /api/v2/arr/<app_name>/customformat-snapshot"""

    def get(self, request, app_name):
        result = services.customformat_snapshot(app_name)
        message = result.pop("message")
        return self.ok(message, **result)
