from django.urls import path

from host_actions.api.views import PacmanSyncView, PacmanUpgradeView, RebootView

app_name = "host_actions_api"

urlpatterns = [
    path("reboot", RebootView.as_view(), name="reboot"),
    path("pacman-sync", PacmanSyncView.as_view(), name="pacman-sync"),
    path("pacman-upgrade", PacmanUpgradeView.as_view(), name="pacman-upgrade"),
]
