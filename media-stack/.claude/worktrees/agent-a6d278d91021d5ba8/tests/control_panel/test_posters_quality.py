"""Phase 04 validation for .claude/plans/control-panel-v3-redesign.plan.md:
services/posters/quality.py's bulk quality-scan heuristics. Pure unit
tests against real PIL-generated image bytes - no FastAPI/auth involved,
same standalone-import style as test_posters_candidates.py.
"""
import importlib
import io
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

CONTROL_PANEL_DIR = Path(__file__).resolve().parent.parent.parent / "control-panel"


@pytest.fixture
def quality(monkeypatch):
    sys.path.insert(0, str(CONTROL_PANEL_DIR))
    sys.modules.pop("services.posters.quality", None)
    sys.modules.pop("services.posters.candidates", None)
    try:
        module = importlib.import_module("services.posters.quality")
        yield module
    finally:
        sys.modules.pop("services.posters.quality", None)
        sys.modules.pop("services.posters.candidates", None)
        sys.path.remove(str(CONTROL_PANEL_DIR))


def _png_bytes(width, height, color=None):
    if color is not None:
        img = Image.new("RGB", (width, height), color)
    else:
        img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _meta(audio_lang_tag=None, tmdb=None):
    guids = [{"id": f"tmdb://{tmdb}"}] if tmdb is not None else []
    media = []
    if audio_lang_tag:
        media = [{"Part": [{"Stream": [
            {"streamType": 1},  # a video stream should be ignored
            {"streamType": 2, "selected": True, "languageTag": audio_lang_tag},
        ]}]}]
    return {"Guid": guids, "Media": media}


def test_flags_small_uniform_grey_image_as_placeholder(quality):
    grey = _png_bytes(680, 1000, color=(45, 45, 45))
    assert quality.scan_item_quality(_meta(), "movie", grey) == ["placeholder"]


def test_does_not_flag_real_looking_high_res_art_as_placeholder(quality):
    real = _png_bytes(1000, 1500)
    flags = quality.scan_item_quality(_meta(), "movie", real)
    assert "placeholder" not in flags


def test_flags_small_dimension_real_art_as_low_res(quality):
    small = _png_bytes(200, 300)
    assert quality.scan_item_quality(_meta(), "movie", small) == ["low_res"]


def test_does_not_flag_large_dimension_art_as_low_res(quality):
    large = _png_bytes(1000, 1500)
    flags = quality.scan_item_quality(_meta(), "movie", large)
    assert "low_res" not in flags


def test_language_mismatch_skipped_when_tmdb_not_configured(quality, monkeypatch):
    monkeypatch.setattr(quality, "TMDB_KEY", None)
    large = _png_bytes(1000, 1500)
    flags = quality.scan_item_quality(_meta(audio_lang_tag="en", tmdb=42), "movie", large)
    assert "language_mismatch" not in flags


def test_language_mismatch_flagged_when_top_poster_language_differs(quality, monkeypatch):
    monkeypatch.setattr(quality, "TMDB_KEY", "test-tmdb-key")
    monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, media_type: 42)
    monkeypatch.setattr(quality, "tmdb_get", lambda path, **params: {
        "posters": [{"iso_639_1": "ja", "vote_average": 8.0, "vote_count": 10}]
    })
    large = _png_bytes(1000, 1500)
    flags = quality.scan_item_quality(_meta(audio_lang_tag="en", tmdb=42), "movie", large)
    assert "language_mismatch" in flags


def test_language_mismatch_not_flagged_when_languages_match(quality, monkeypatch):
    monkeypatch.setattr(quality, "TMDB_KEY", "test-tmdb-key")
    monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, media_type: 42)
    monkeypatch.setattr(quality, "tmdb_get", lambda path, **params: {
        "posters": [{"iso_639_1": "en", "vote_average": 8.0, "vote_count": 10}]
    })
    large = _png_bytes(1000, 1500)
    flags = quality.scan_item_quality(_meta(audio_lang_tag="en", tmdb=42), "movie", large)
    assert "language_mismatch" not in flags


def test_language_mismatch_not_flagged_for_textless_top_poster(quality, monkeypatch):
    monkeypatch.setattr(quality, "TMDB_KEY", "test-tmdb-key")
    monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, media_type: 42)
    monkeypatch.setattr(quality, "tmdb_get", lambda path, **params: {
        "posters": [{"iso_639_1": None, "vote_average": 9.0, "vote_count": 50}]
    })
    large = _png_bytes(1000, 1500)
    flags = quality.scan_item_quality(_meta(audio_lang_tag="en", tmdb=42), "movie", large)
    assert "language_mismatch" not in flags


def test_no_audio_track_skips_language_check(quality, monkeypatch):
    monkeypatch.setattr(quality, "TMDB_KEY", "test-tmdb-key")
    large = _png_bytes(1000, 1500)
    flags = quality.scan_item_quality(_meta(tmdb=42), "movie", large)
    assert "language_mismatch" not in flags


def test_corrupt_image_bytes_does_not_crash_and_flags_nothing(quality):
    assert quality.scan_item_quality(_meta(), "movie", b"not an image") == []
