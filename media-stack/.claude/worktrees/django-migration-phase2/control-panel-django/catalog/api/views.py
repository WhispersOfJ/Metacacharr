"""Curated software catalog routes - list/status/install/remove for the
vetted programs in catalog/registry.py. Ported from
control-panel/services/catalog/router.py.

list/status use the default permission (IsAuthenticatedOrServiceKey) so
the catalog grid can render without a session hiccup. install/remove are
manual UI actions with no automation caller, so they require
IsAuthenticatedSessionOnly and gate on confirm=true in the view BEFORE
calling into services - matching host_actions' _ConfirmedActionView
pattern (see host_actions/api/views.py) and Task 7's review-fixed
landmine around it.
"""
from core.api_base import EnvelopeAPIView, ServiceError
from core.permissions import IsAuthenticatedSessionOnly
from catalog import services
from catalog.api.serializers import InstallRequestSerializer, RemoveRequestSerializer


class CatalogListView(EnvelopeAPIView):
    def get(self, request):
        result = services.list_catalog()
        return self.ok(result["message"], items=result["items"])


class CatalogStatusView(EnvelopeAPIView):
    def get(self, request, catalog_id):
        result = services.get_status(catalog_id)
        extra = {k: v for k, v in result.items() if k != "message"}
        return self.ok(result["message"], **extra)


class CatalogInstallView(EnvelopeAPIView):
    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request, catalog_id):
        body = InstallRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not body.validated_data["confirm"]:
            raise ServiceError(
                "Set confirm=true to install - this pulls an image and starts a real container.",
                status=400,
            )
        result = services.install(catalog_id)
        return self.ok(result["message"], ports=result["ports"])


class CatalogRemoveView(EnvelopeAPIView):
    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request, catalog_id):
        body = RemoveRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not body.validated_data["confirm"]:
            raise ServiceError("Set confirm=true to remove.", status=400)
        result = services.remove(catalog_id, remove_volumes=body.validated_data["remove_volumes"])
        return self.ok(result["message"])
