"""Server-Sent-Events response helper shared by the three posters stream
views (sync/review/scan). SSE isn't a JSON envelope response, so this
wraps a plain generator (already yielding "data: ...\n\n" lines, built by
posters.services.{sync,review,scan}_stream) in a StreamingHttpResponse
instead of going through EnvelopeAPIView.ok()/core.api_base.
"""
from django.http import StreamingHttpResponse


def sse_response(generator) -> StreamingHttpResponse:
    return StreamingHttpResponse(generator, content_type="text/event-stream")
