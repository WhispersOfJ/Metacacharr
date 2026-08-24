from django.urls import path

from letterboxd.api.views import (
    AddFromListView,
    AddView,
    HistoryView,
    SyncTickView,
    TrackedView,
    TrackView,
    UntrackView,
)

app_name = "letterboxd_api"

urlpatterns = [
    path("add", AddView.as_view(), name="add"),
    path("add-from-list", AddFromListView.as_view(), name="add-from-list"),
    path("history", HistoryView.as_view(), name="history"),
    path("track", TrackView.as_view(), name="track"),
    path("untrack", UntrackView.as_view(), name="untrack"),
    path("tracked", TrackedView.as_view(), name="tracked"),
    path("sync-tick", SyncTickView.as_view(), name="sync-tick"),
]
