from django.urls import path

from nzbdav.api.views import (
    DedupConfigCheckView,
    DeleteFailuresView,
    HistoryView,
    QueueView,
    StatsView,
)

app_name = "nzbdav_api"

urlpatterns = [
    path("queue", QueueView.as_view(), name="queue"),
    path("history", HistoryView.as_view(), name="history"),
    path("dedup-config-check", DedupConfigCheckView.as_view(), name="dedup-config-check"),
    path("stats", StatsView.as_view(), name="stats"),
    path("delete-failures", DeleteFailuresView.as_view(), name="delete-failures"),
]
