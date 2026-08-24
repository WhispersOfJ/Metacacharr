from rest_framework.test import APIRequestFactory, force_authenticate

from core.api_base import EnvelopeAPIView, ServiceError, envelope_exception_handler


class _DummyView(EnvelopeAPIView):
    def get(self, request):
        return self.ok("did the thing", count=3)


class _FailingView(EnvelopeAPIView):
    def get(self, request):
        raise ServiceError("upstream unreachable", status=503)


class _FakeAuthedUser:
    """Duck-types core.authentication's real return values well enough to
    satisfy IsAuthenticatedOrServiceKey without touching the database —
    EnvelopeAPIView's permission_classes gate every request, so exercising
    self.ok()/ServiceError rendering here requires an authenticated caller,
    same as the app.py-era routes did behind current_user_or_service."""

    is_authenticated = True


def test_ok_helper_shapes_envelope():
    request = APIRequestFactory().get("/x")
    request.session = {}
    force_authenticate(request, user=_FakeAuthedUser())
    response = _DummyView.as_view()(request)
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["message"] == "did the thing"
    assert response.data["count"] == 3
    assert "time" in response.data


def test_service_error_renders_envelope_with_custom_status():
    request = APIRequestFactory().get("/x")
    request.session = {}
    force_authenticate(request, user=_FakeAuthedUser())
    response = _FailingView.as_view()(request)
    assert response.status_code == 503
    assert response.data == {"ok": False, "message": "upstream unreachable"}


def test_envelope_exception_handler_ignores_non_service_errors():
    assert envelope_exception_handler(ValueError("boom"), {}) is None


def test_service_error_logs_server_side_before_rendering(caplog):
    """Mirrors FastAPI-era core.responses.fail(), which always did
    logger.error(message) before raising - restored in Finding 1's fix
    as centralized logging in ServiceError.__init__ rather than
    re-adding logger.error() at each of the 28 ported call sites."""
    with caplog.at_level("ERROR", logger="core.api_base"):
        request = APIRequestFactory().get("/x")
        request.session = {}
        force_authenticate(request, user=_FakeAuthedUser())
        response = _FailingView.as_view()(request)

    assert response.status_code == 503
    assert any(record.message == "upstream unreachable" for record in caplog.records)
