from core.api_base import EnvelopeAPIView
from sonarr import services


class MonitorEpisodesFixView(EnvelopeAPIView):
    """Fix drifted episode-monitoring state under monitored series.
    Default tier (IsAuthenticatedOrServiceKey) - called unattended via
    service key by stack-sonarr-monitor-episodes-fix.fish."""

    def post(self, request):
        return self.ok("Episode monitoring fixed", **services.fix_monitored_episodes())
