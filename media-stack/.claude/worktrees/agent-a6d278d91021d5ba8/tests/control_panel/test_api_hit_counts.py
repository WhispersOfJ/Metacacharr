"""Gate tests for core/api_hit_counts.py - outbound API hit counter used by
the dashboard's per-service badges. First-ever coverage for this module."""
import pytest


@pytest.fixture
def hit_counts_module(cp_main_app):
    import core.api_hit_counts as module
    module._API_HOST_LABELS.clear()
    module.API_HIT_COUNTS.clear()
    module._patched = False
    yield module
    module._patched = False


def test_register_host_label_seeds_zero_count(hit_counts_module):
    hit_counts_module.register_host_label("http://radarr:7878", "Radarr")
    assert hit_counts_module.API_HIT_COUNTS["Radarr"] == 0


def test_register_host_label_skips_url_without_host(hit_counts_module):
    hit_counts_module.register_host_label("not-a-url", "Nothing")
    assert "Nothing" not in hit_counts_module.API_HIT_COUNTS


def test_counted_request_increments_registered_label(hit_counts_module, monkeypatch):
    hit_counts_module.register_host_label("http://radarr:7878", "Radarr")
    monkeypatch.setattr(hit_counts_module, "_original_request", lambda method, url, *a, **k: "response")
    result = hit_counts_module._counted_request("GET", "http://radarr:7878/api/v3/queue")
    assert result == "response"
    assert hit_counts_module.API_HIT_COUNTS["Radarr"] == 1


def test_counted_request_unregistered_host_uses_hostname(hit_counts_module, monkeypatch):
    monkeypatch.setattr(hit_counts_module, "_original_request", lambda method, url, *a, **k: "response")
    hit_counts_module._counted_request("GET", "http://unknown-host:1234/x")
    assert hit_counts_module.API_HIT_COUNTS["unknown-host"] == 1


def test_install_is_idempotent(hit_counts_module):
    hit_counts_module.install()
    patched_request = hit_counts_module.httpx.request
    hit_counts_module.install()
    assert hit_counts_module.httpx.request is patched_request
