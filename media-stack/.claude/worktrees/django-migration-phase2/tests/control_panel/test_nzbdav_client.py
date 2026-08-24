"""Gate tests for core/nzbdav_client.py. First-ever coverage for this
module - moved out of arr_client.py in Phase 4 but never got its own tests."""
from unittest.mock import MagicMock

import httpx
import pytest


@pytest.fixture
def nzbdav_client_module(cp_main_app):
    import core.nzbdav_client as module
    return module


def test_nzbdav_api_missing_key_fails_503(nzbdav_client_module, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(nzbdav_client_module, "NZBDAV_API_KEY", None)
    with pytest.raises(HTTPException) as exc:
        nzbdav_client_module.nzbdav_api("queue")
    assert exc.value.status_code == 503


def test_nzbdav_api_success_returns_json(nzbdav_client_module, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"queue": []}
        return resp

    monkeypatch.setattr(nzbdav_client_module.httpx, "get", fake_get)
    assert nzbdav_client_module.nzbdav_api("queue") == {"queue": []}


def test_nzbdav_api_http_error_fails_502(nzbdav_client_module, monkeypatch):
    from fastapi import HTTPException

    def raise_error(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(nzbdav_client_module.httpx, "get", raise_error)
    with pytest.raises(HTTPException) as exc:
        nzbdav_client_module.nzbdav_api("queue")
    assert exc.value.status_code == 502
