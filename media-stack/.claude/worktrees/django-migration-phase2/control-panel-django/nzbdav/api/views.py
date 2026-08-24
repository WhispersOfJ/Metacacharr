from core.api_base import EnvelopeAPIView
from nzbdav import services
from nzbdav.api.serializers import HistoryQuerySerializer


class QueueView(EnvelopeAPIView):
    def get(self, request):
        items = services.get_queue()
        return self.ok(f"{len(items)} item(s) in queue.", items=items)


class HistoryView(EnvelopeAPIView):
    def get(self, request):
        query = HistoryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        items = services.get_history(limit=query.validated_data["limit"])
        return self.ok(f"{len(items)} history item(s).", items=items)


class DedupConfigCheckView(EnvelopeAPIView):
    def get(self, request):
        result = services.check_dedup_config()
        message = result.pop("message")
        return self.ok(message, **result)


class StatsView(EnvelopeAPIView):
    def get(self, request):
        result = services.get_stats()
        message = result.pop("message")
        return self.ok(message, **result)


class DeleteFailuresView(EnvelopeAPIView):
    def post(self, request):
        result = services.delete_failures()
        message = result.pop("message")
        return self.ok(message, **result)
