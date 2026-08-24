from django.urls import path

from host.api.views import (
    ContainersView,
    ContainerLogsStreamView,
    ContainerRestartView,
    ContainerStartView,
    ContainerStopView,
    DiskHealthView,
    DiskUsageView,
    DocsReadmeView,
    HostResourcesView,
    ImageCheckView,
    LogLevelsView,
    MountHealthView,
    NotifyTestView,
    OomCheckView,
    PermsCheckView,
    PruneDiskView,
    ResetLogLevelsView,
    ResourceCheckView,
    RestartAllView,
    SettingsView,
    StatusView,
    TopView,
    VersionView,
)

app_name = "host_api"

# All mounted under /api/v2/host/ in config/urls.py. Shares that prefix
# with host_actions.api.urls (reboot/pacman-sync/pacman-upgrade) - no
# suffix collisions with this app's 24 paths, so both include() entries
# coexist (verified against the Task 7 path list).
urlpatterns = [
    path("status", StatusView.as_view(), name="status"),
    path("containers", ContainersView.as_view(), name="containers"),
    path("container/<str:name>/restart", ContainerRestartView.as_view(), name="container_restart"),
    path("container/<str:name>/stop", ContainerStopView.as_view(), name="container_stop"),
    path("container/<str:name>/start", ContainerStartView.as_view(), name="container_start"),
    path("container/<str:name>/logs/stream", ContainerLogsStreamView.as_view(), name="container_logs_stream"),
    path("stack/restart-all", RestartAllView.as_view(), name="restart_all"),
    path("settings", SettingsView.as_view(), name="settings"),
    path("resource-check", ResourceCheckView.as_view(), name="resource_check"),
    path("disk-health", DiskHealthView.as_view(), name="disk_health"),
    path("disk-health/prune", PruneDiskView.as_view(), name="disk_health_prune"),
    path("host-resources", HostResourcesView.as_view(), name="host_resources"),
    path("log-levels", LogLevelsView.as_view(), name="log_levels"),
    path("log-levels/reset", ResetLogLevelsView.as_view(), name="log_levels_reset"),
    path("oom-check", OomCheckView.as_view(), name="oom_check"),
    path("disk-usage", DiskUsageView.as_view(), name="disk_usage"),
    path("mount-health", MountHealthView.as_view(), name="mount_health"),
    path("perms-check", PermsCheckView.as_view(), name="perms_check"),
    path("image-check", ImageCheckView.as_view(), name="image_check"),
    path("version", VersionView.as_view(), name="version"),
    path("docs/readme", DocsReadmeView.as_view(), name="docs_readme"),
    path("notify/test", NotifyTestView.as_view(), name="notify_test"),
    path("top", TopView.as_view(), name="top"),
]
