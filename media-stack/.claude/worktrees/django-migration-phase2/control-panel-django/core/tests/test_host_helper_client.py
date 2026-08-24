import pytest

from core.api_base import ServiceError
from core.host_helper_client import DEFAULT_TIMEOUT, HOST_HELPER_SOCKET, call_host_helper


def test_host_helper_socket_and_timeout_constants_exist():
    assert isinstance(HOST_HELPER_SOCKET, str)
    assert isinstance(DEFAULT_TIMEOUT, (int, float))


def test_call_host_helper_raises_service_error_when_socket_missing(tmp_path, monkeypatch):
    missing_socket = str(tmp_path / "does-not-exist.sock")
    monkeypatch.setattr("core.host_helper_client.HOST_HELPER_SOCKET", missing_socket)
    with pytest.raises(ServiceError) as exc_info:
        call_host_helper("some-action")
    assert exc_info.value.status_code == 503
