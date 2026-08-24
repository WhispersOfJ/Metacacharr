from core.api_base import EnvelopeAPIView
from queue_app import services


class QueueStatusView(EnvelopeAPIView):
    def get(self, request):
        return self.ok("Queue status", queues=services.aggregate_queue_status())
