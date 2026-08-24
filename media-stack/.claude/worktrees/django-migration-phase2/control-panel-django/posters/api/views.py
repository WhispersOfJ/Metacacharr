"""Poster-sync/review/scan routes, ported from
control-panel/services/posters/router.py. Every view uses the default
EnvelopeAPIView tier (IsAuthenticatedOrServiceKey) - matches the
FastAPI-era current_user_or_service dependency used on every route in the
source file (no session-only routes in this app).

The three *_stream views and ThumbView are NOT EnvelopeAPIView subclasses
(SSE/raw-image responses aren't the {ok, message} JSON envelope), but they
still enforce the same auth: rest_framework.views.APIView picks up this
project's DEFAULT_AUTHENTICATION_CLASSES/DEFAULT_PERMISSION_CLASSES
(config/settings.py REST_FRAMEWORK) automatically, which are already
SessionOrApiKeyAuthentication/IsAuthenticatedOrServiceKey - the same pair
EnvelopeAPIView sets explicitly - so no override is needed here. Returning
a StreamingHttpResponse/HttpResponse (rather than a DRF Response) from
APIView.get() works unchanged: DRF's finalize_response() only special-cases
actual Response instances for content negotiation, and passes any other
HttpResponseBase subclass through untouched.
"""
from django.http import HttpResponse
from rest_framework.views import APIView

from core.api_base import EnvelopeAPIView
from posters import services
from posters.api.serializers import (
    ApplyRequestSerializer,
    GalleryQuerySerializer,
    ReviewRequestSerializer,
    ScanRequestSerializer,
    SyncRequestSerializer,
)
from posters.api.sse import sse_response


class LibrariesView(EnvelopeAPIView):
    """GET /api/v2/posters/libraries."""

    def get(self, request):
        result = services.list_libraries()
        message = result.pop("message")
        return self.ok(message, **result)


class SyncView(EnvelopeAPIView):
    """POST /api/v2/posters/sync."""

    def post(self, request):
        serializer = SyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        message = services.start_sync(data["library"], data["dry_run"], data["source"])
        return self.ok(message)


class SyncStreamView(APIView):
    """GET /api/v2/posters/sync/stream."""

    def get(self, request):
        return sse_response(services.sync_stream())


class ReviewView(EnvelopeAPIView):
    """POST /api/v2/posters/review."""

    def post(self, request):
        serializer = ReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        message = services.start_review(data["library"], data["source"])
        return self.ok(message)


class ReviewStreamView(APIView):
    """GET /api/v2/posters/review/stream."""

    def get(self, request):
        return sse_response(services.review_stream())


class ApplyView(EnvelopeAPIView):
    """POST /api/v2/posters/apply."""

    def post(self, request):
        serializer = ApplyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        message = services.apply_poster(data["rating_key"], data["url"])
        return self.ok(message)


class GalleryView(EnvelopeAPIView):
    """GET /api/v2/posters/gallery?library=...&offset=...&limit=..."""

    def get(self, request):
        query = GalleryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        result = services.gallery(data["library"], data["offset"], data["limit"])
        message = result.pop("message")
        return self.ok(message, **result)


class ThumbView(APIView):
    """GET /api/v2/posters/thumb/<rating_key>."""

    def get(self, request, rating_key):
        content, content_type = services.thumb(rating_key)
        return HttpResponse(content=content, content_type=content_type)


class ScanView(EnvelopeAPIView):
    """POST /api/v2/posters/scan."""

    def post(self, request):
        serializer = ScanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        message = services.start_scan(data["library"])
        return self.ok(message)


class ScanStreamView(APIView):
    """GET /api/v2/posters/scan/stream."""

    def get(self, request):
        return sse_response(services.scan_stream())
