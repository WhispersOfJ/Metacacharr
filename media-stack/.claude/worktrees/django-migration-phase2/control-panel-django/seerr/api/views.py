from core.api_base import EnvelopeAPIView
from seerr import services
from seerr.api.serializers import SeerrQuerySerializer


class SeerrRequestsView(EnvelopeAPIView):
    def get(self, request):
        query = SeerrQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        status = query.validated_data["status"]
        items = services.list_requests(status)
        return self.ok(f"{len(items)} {status} request(s) in Seerr.", items=items)
