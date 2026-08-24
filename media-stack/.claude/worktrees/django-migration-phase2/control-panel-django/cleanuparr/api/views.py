from core.api_base import EnvelopeAPIView
from cleanuparr import services
from cleanuparr.api.serializers import StrikesQuerySerializer


class InstancesView(EnvelopeAPIView):
    def get(self, request):
        result = services.check_instances()
        message = result.pop("message")
        return self.ok(message, **result)


class StrikesView(EnvelopeAPIView):
    def get(self, request):
        query = StrikesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.recent_strikes(limit=query.validated_data["limit"])
        message = result.pop("message")
        return self.ok(message, **result)
