from core.api_base import EnvelopeAPIView
from core.permissions import IsAuthenticatedSessionOnly
from radarr import services
from radarr.api.serializers import ExcludeRequestSerializer


class ExcludeMovieView(EnvelopeAPIView):
    """Exclude a movie from Radarr import lists.
    Session-only (no API key) - prevents accidental exclusions via service accounts."""

    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request):
        body = ExcludeRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = services.exclude_movie(body.validated_data["movieId"])
        return self.ok("Movie excluded", **result)
