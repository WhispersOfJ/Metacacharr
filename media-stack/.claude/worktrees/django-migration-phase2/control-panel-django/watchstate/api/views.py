from core.api_base import EnvelopeAPIView
from watchstate import services
from watchstate.api.serializers import HistoryQuerySerializer


class StatusView(EnvelopeAPIView):
    def get(self, request):
        result = services.get_status()
        message = result.pop("message")
        return self.ok(message, **result)


class ImportView(EnvelopeAPIView):
    def post(self, request):
        result = services.queue_import()
        message = result.pop("message")
        return self.ok(message, **result)


class HistoryView(EnvelopeAPIView):
    def get(self, request):
        query = HistoryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.get_history(
            item=query.validated_data["item"],
            limit=query.validated_data["limit"],
        )
        message = result.pop("message")
        return self.ok(message, **result)
