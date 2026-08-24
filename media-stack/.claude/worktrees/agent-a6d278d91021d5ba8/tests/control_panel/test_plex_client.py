"""Gate tests for core/plex_client.py. First-ever coverage for this module."""
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def plex_client_module(cp_main_app):
    import core.plex_client as module
    return module


def test_plex_headers_missing_config_fails_503(plex_client_module, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(plex_client_module, "PLEX_URL", "")
    monkeypatch.setattr(plex_client_module, "PLEX_TOKEN", None)
    with pytest.raises(HTTPException) as exc:
        plex_client_module.plex_headers()
    assert exc.value.status_code == 503


def test_plex_headers_returns_token_header(plex_client_module, monkeypatch):
    monkeypatch.setattr(plex_client_module, "PLEX_URL", "http://test-plex:32400")
    monkeypatch.setattr(plex_client_module, "PLEX_TOKEN", "abc123")
    headers = plex_client_module.plex_headers()
    assert headers["X-Plex-Token"] == "abc123"


def test_plex_sections_returns_directory_list(plex_client_module, monkeypatch):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"MediaContainer": {"Directory": [{"title": "Movies"}]}}
    monkeypatch.setattr(plex_client_module.httpx, "get", lambda *a, **k: resp)
    sections = plex_client_module.plex_sections()
    assert sections == [{"title": "Movies"}]


def test_plex_sections_missing_directory_key_returns_empty(plex_client_module, monkeypatch):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"MediaContainer": {}}
    monkeypatch.setattr(plex_client_module.httpx, "get", lambda *a, **k: resp)
    assert plex_client_module.plex_sections() == []
