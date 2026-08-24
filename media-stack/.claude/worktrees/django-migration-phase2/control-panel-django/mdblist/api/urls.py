from django.urls import path

from mdblist.api.views import (
    HistoryView,
    ImportListView,
    SyncTickView,
    TrackedView,
    TrackView,
    UntrackView,
)

app_name = "mdblist_api"

urlpatterns = [
    path("import-list", ImportListView.as_view(), name="import-list"),
    path("history", HistoryView.as_view(), name="history"),
    path("track", TrackView.as_view(), name="track"),
    path("untrack", UntrackView.as_view(), name="untrack"),
    path("tracked", TrackedView.as_view(), name="tracked"),
    path("sync-tick", SyncTickView.as_view(), name="sync-tick"),
]
