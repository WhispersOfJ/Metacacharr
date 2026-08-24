import json

import httpx
import pytest

from core.api_base import ServiceError
from seerr.services import list_requests


def _settings_path(tmp_path, monkeypatch):
    config_dir = tmp_path / "host-config"
    (config_dir / "seerr").mkdir(parents=True)
    monkeypatch.setattr("seerr.services.HOST_CONFIG_DIR", str(config_dir))
    return config_dir / "seerr" / "settings.json"


def test_list_requests_success(httpx_mock, tmp_path, monkeypatch):
    settings_path = _settings_path(tmp_path, monkeypatch)
    settings_path.write_text(json.dumps({"main": {"apiKey": "test-seerr-key"}}))
    httpx_mock.add_response(
        url="http://seerr:5055/api/v1/request?filter=pending&take=25",
        json={
            "results": [
                {
                    "media": {"externalServiceSlug": "the-matrix", "mediaType": "movie"},
                    "requestedBy": {"displayName": "Bear"},
                    "status": 2,
                    "createdAt": "2026-01-01T00:00:00.000Z",
                }
            ]
        },
    )
    items = list_requests("pending")
    assert items == [
        {
            "title": "the-matrix",
            "type": "movie",
            "requestedBy": "Bear",
            "status": 2,
            "createdAt": "2026-01-01T00:00:00.000Z",
        }
    ]


def test_list_requests_falls_back_to_tmdb_id_when_no_slug(httpx_mock, tmp_path, monkeypatch):
    settings_path = _settings_path(tmp_path, monkeypatch)
    settings_path.write_text(json.dumps({"main": {"apiKey": "test-seerr-key"}}))
    httpx_mock.add_response(
        url="http://seerr:5055/api/v1/request?filter=pending&take=25",
        json={
            "results": [
                {
                    "media": {"tmdbId": 603, "mediaType": "movie"},
                    "requestedBy": {"displayName": "Bear"},
                    "status": 2,
                    "createdAt": "2026-01-01T00:00:00.000Z",
                }
            ]
        },
    )
    items = list_requests("pending")
    assert items[0]["title"] == "tmdb:603"


def test_list_requests_empty_results(httpx_mock, tmp_path, monkeypatch):
    settings_path = _settings_path(tmp_path, monkeypatch)
    settings_path.write_text(json.dumps({"main": {"apiKey": "test-seerr-key"}}))
    httpx_mock.add_response(
        url="http://seerr:5055/api/v1/request?filter=pending&take=25",
        json={"results": []},
    )
    assert list_requests("pending") == []


def test_list_requests_missing_settings_file_raises_503(tmp_path, monkeypatch):
    config_dir = tmp_path / "host-config"
    config_dir.mkdir()
    monkeypatch.setattr("seerr.services.HOST_CONFIG_DIR", str(config_dir))
    with pytest.raises(ServiceError) as exc_info:
        list_requests("pending")
    assert exc_info.value.status_code == 503


def test_list_requests_unreadable_settings_file_raises_503(tmp_path, monkeypatch):
    settings_path = _settings_path(tmp_path, monkeypatch)
    settings_path.write_text("not valid json {{{")
    with pytest.raises(ServiceError) as exc_info:
        list_requests("pending")
    assert exc_info.value.status_code == 503


def test_list_requests_upstream_transport_error_raises_service_error(httpx_mock, tmp_path, monkeypatch):
    settings_path = _settings_path(tmp_path, monkeypatch)
    settings_path.write_text(json.dumps({"main": {"apiKey": "test-seerr-key"}}))
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    with pytest.raises(ServiceError):
        list_requests("pending")


def test_list_requests_upstream_http_error_raises_service_error(httpx_mock, tmp_path, monkeypatch):
    settings_path = _settings_path(tmp_path, monkeypatch)
    settings_path.write_text(json.dumps({"main": {"apiKey": "test-seerr-key"}}))
    httpx_mock.add_response(status_code=500)
    with pytest.raises(ServiceError):
        list_requests("pending")
