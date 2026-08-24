from django.urls import path

from catalog.api.views import CatalogInstallView, CatalogListView, CatalogRemoveView, CatalogStatusView

app_name = "catalog_api"

urlpatterns = [
    path("", CatalogListView.as_view(), name="list"),
    path("<str:catalog_id>/status", CatalogStatusView.as_view(), name="status"),
    path("<str:catalog_id>/install", CatalogInstallView.as_view(), name="install"),
    path("<str:catalog_id>/remove", CatalogRemoveView.as_view(), name="remove"),
]
