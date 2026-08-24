from core.api_base import EnvelopeAPIView
from prowlarr import services


class ProwlarrIndexersView(EnvelopeAPIView):
    def get(self, request):
        items = services.list_indexers()
        return self.ok("Indexers fetched", items=items)
