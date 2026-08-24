from django.urls import path

from sonarr.api.views import MonitorEpisodesFixView

app_name = "sonarr_api"

urlpatterns = [
    path("monitor-episodes-fix", MonitorEpisodesFixView.as_view(), name="monitor_episodes_fix"),
]
