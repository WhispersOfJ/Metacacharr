from django.urls import path

from posters.api.views import (
    ApplyView,
    GalleryView,
    LibrariesView,
    ReviewStreamView,
    ReviewView,
    ScanStreamView,
    ScanView,
    SyncStreamView,
    SyncView,
    ThumbView,
)

app_name = "posters_api"

urlpatterns = [
    path("libraries", LibrariesView.as_view(), name="libraries"),
    path("sync", SyncView.as_view(), name="sync"),
    path("sync/stream", SyncStreamView.as_view(), name="sync-stream"),
    path("review", ReviewView.as_view(), name="review"),
    path("review/stream", ReviewStreamView.as_view(), name="review-stream"),
    path("apply", ApplyView.as_view(), name="apply"),
    path("gallery", GalleryView.as_view(), name="gallery"),
    path("thumb/<str:rating_key>", ThumbView.as_view(), name="thumb"),
    path("scan", ScanView.as_view(), name="scan"),
    path("scan/stream", ScanStreamView.as_view(), name="scan-stream"),
]
