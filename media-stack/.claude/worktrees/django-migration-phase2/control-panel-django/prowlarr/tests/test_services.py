import httpx
import pytest

from core.api_base import ServiceError
from prowlarr.services import list_indexers


def test_list_indexers_success(httpx_mock):
    """Prowlarr /api/v1/indexer returns list of indexers sorted by name."""
    httpx_mock.add_response(
        url="http://prowlarr:9696/api/v1/indexer",
        json=[
            {"name": "Zebra Indexer", "enable": True, "priority": 50},
            {"name": "Alpha Indexer", "enable": False, "priority": 25},
            {"name": "Beta Indexer", "enable": True, "priority": 30},
        ],
    )
    items = list_indexers()
    assert items == [
        {"name": "Alpha Indexer", "enabled": False, "priority": 25},
        {"name": "Beta Indexer", "enabled": True, "priority": 30},
        {"name": "Zebra Indexer", "enabled": True, "priority": 50},
    ]


def test_list_indexers_missing_key_raises_503(monkeypatch):
    """Missing PROWLARR_API_KEY raises ServiceError with 503 status."""
    from core import arr_client
    monkeypatch.setitem(arr_client.PROWLARR_CFG, "key", None)
    with pytest.raises(ServiceError) as exc_info:
        list_indexers()
    assert exc_info.value.status_code == 503


def test_list_indexers_handles_none_name(httpx_mock):
    """Indexers with None names sort first (as empty strings)."""
    httpx_mock.add_response(
        url="http://prowlarr:9696/api/v1/indexer",
        json=[
            {"name": "Alpha", "enable": True, "priority": 10},
            {"name": None, "enable": True, "priority": 20},
            {"name": "Bravo", "enable": True, "priority": 30},
        ],
    )
    items = list_indexers()
    assert items[0]["name"] is None
    assert items[1]["name"] == "Alpha"
    assert items[2]["name"] == "Bravo"


def test_list_indexers_upstream_error_raises_service_error(httpx_mock):
    """HTTP errors from Prowlarr raise ServiceError."""
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    with pytest.raises(ServiceError):
        list_indexers()
