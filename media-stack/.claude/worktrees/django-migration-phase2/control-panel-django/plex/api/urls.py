from django.urls import path

from plex.api.views import (
    AnalyzeView,
    ButlerTaskView,
    CleanBundlesView,
    DuplicatesView,
    EmptyTrashView,
    LibrariesView,
    OptimizeDbView,
    RecentlyAddedView,
    ScanHealthView,
    ScanView,
    SessionsView,
    TmdbMissingView,
    UpdatesView,
)

app_name = "plex_api"

urlpatterns = [
    path("scan", ScanView.as_view(), name="scan"),
    path("libraries", LibrariesView.as_view(), name="libraries"),
    path("empty-trash", EmptyTrashView.as_view(), name="empty-trash"),
    path("analyze", AnalyzeView.as_view(), name="analyze"),
    path("optimize-db", OptimizeDbView.as_view(), name="optimize-db"),
    path("clean-bundles", CleanBundlesView.as_view(), name="clean-bundles"),
    path("butler/<str:task>", ButlerTaskView.as_view(), name="butler-task"),
    path("updates", UpdatesView.as_view(), name="updates"),
    path("scan-health", ScanHealthView.as_view(), name="scan-health"),
    path("duplicates", DuplicatesView.as_view(), name="duplicates"),
    path("tmdb-missing", TmdbMissingView.as_view(), name="tmdb-missing"),
    path("sessions", SessionsView.as_view(), name="sessions"),
    path("recently-added", RecentlyAddedView.as_view(), name="recently-added"),
]
