from core.arr_client import ARR_APPS, PROWLARR_CFG, QUEUE_ARR_APPS, RADARR_APPS, format_eta, human_size


def test_arr_apps_registry_is_populated():
    assert "radarr" in ARR_APPS
    assert "sonarr" in ARR_APPS


def test_prowlarr_cfg_has_url_and_key_fields():
    assert "url" in PROWLARR_CFG or hasattr(PROWLARR_CFG, "url")


def test_queue_and_radarr_app_subsets_are_populated():
    assert len(QUEUE_ARR_APPS) >= 1
    assert len(RADARR_APPS) >= 1


def test_human_size_formats_bytes_up_through_units():
    assert human_size(None) == "?"
    assert human_size(0) == "?"
    assert human_size(512) == "512.0 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(1024 * 1024 * 3) == "3.0 MB"


def test_format_eta_formats_seconds_up_through_days():
    assert format_eta(-1) == "unknown"
    assert format_eta(float("inf")) == "unknown"
    assert format_eta(45) == "45s"
    assert format_eta(125) == "2m05s"
    assert format_eta(3725) == "1h02m"
    assert format_eta(90000) == "1d01h"
