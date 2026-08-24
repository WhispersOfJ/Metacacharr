import io

import pytest
from PIL import Image

from posters import quality


def _png(size, color) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


PLACEHOLDER_BYTES = _png((1, 1), (50, 50, 50))
LOW_RES_BYTES = _png((100, 100), (255, 0, 0))
GOOD_BYTES = _png((500, 500), (255, 0, 0))


class TestIsPlaceholder:
    def test_small_grey_image_is_placeholder(self):
        assert quality._is_placeholder(PLACEHOLDER_BYTES) is True

    def test_large_file_is_not_placeholder(self):
        big = b"\x00" * (quality.PLACEHOLDER_MAX_BYTES + 1)
        assert quality._is_placeholder(big) is False

    def test_unparseable_bytes_is_not_placeholder(self):
        assert quality._is_placeholder(b"not an image") is False

    def test_small_colorful_image_is_not_placeholder(self):
        assert quality._is_placeholder(LOW_RES_BYTES) is False


class TestPosterDimensions:
    def test_valid_image(self):
        assert quality._poster_dimensions(GOOD_BYTES) == (500, 500)

    def test_unparseable_returns_none(self):
        assert quality._poster_dimensions(b"not an image") is None


class TestPrimaryAudioLang:
    def test_prefers_language_tag(self):
        meta = {"Media": [{"Part": [{"Stream": [
            {"streamType": 2, "selected": True, "languageTag": "EN", "languageCode": "eng"},
        ]}]}]}
        assert quality._primary_audio_lang(meta) == "en"

    def test_falls_back_to_language_code_mapping(self):
        meta = {"Media": [{"Part": [{"Stream": [
            {"streamType": 2, "selected": True, "languageCode": "jpn"},
        ]}]}]}
        assert quality._primary_audio_lang(meta) == "ja"

    def test_unmapped_code_returns_none(self):
        meta = {"Media": [{"Part": [{"Stream": [
            {"streamType": 2, "selected": True, "languageCode": "xyz"},
        ]}]}]}
        assert quality._primary_audio_lang(meta) is None

    def test_no_selected_audio_stream_returns_none(self):
        meta = {"Media": [{"Part": [{"Stream": [
            {"streamType": 3, "selected": True, "languageCode": "eng"},
        ]}]}]}
        assert quality._primary_audio_lang(meta) is None

    def test_no_streams_returns_none(self):
        assert quality._primary_audio_lang({}) is None


class TestLanguageMismatch:
    def test_no_tmdb_key_never_flags(self, monkeypatch):
        monkeypatch.setattr(quality, "TMDB_KEY", None)
        assert quality._language_mismatch({}, "movie") is False

    def test_no_audio_lang_never_flags(self, monkeypatch):
        monkeypatch.setattr(quality, "TMDB_KEY", "key")
        monkeypatch.setattr(quality, "_primary_audio_lang", lambda meta: None)
        assert quality._language_mismatch({}, "movie") is False

    def test_no_tmdb_id_never_flags(self, monkeypatch):
        monkeypatch.setattr(quality, "TMDB_KEY", "key")
        monkeypatch.setattr(quality, "_primary_audio_lang", lambda meta: "en")
        monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, mt: None)
        assert quality._language_mismatch({}, "movie") is False

    def test_tmdb_lookup_error_never_flags(self, monkeypatch):
        monkeypatch.setattr(quality, "TMDB_KEY", "key")
        monkeypatch.setattr(quality, "_primary_audio_lang", lambda meta: "en")
        monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, mt: 1)

        def _boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(quality, "tmdb_get", _boom)
        assert quality._language_mismatch({}, "movie") is False

    def test_no_posters_never_flags(self, monkeypatch):
        monkeypatch.setattr(quality, "TMDB_KEY", "key")
        monkeypatch.setattr(quality, "_primary_audio_lang", lambda meta: "en")
        monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, mt: 1)
        monkeypatch.setattr(quality, "tmdb_get", lambda path: {"posters": []})
        assert quality._language_mismatch({}, "movie") is False

    def test_textless_top_poster_never_flags(self, monkeypatch):
        monkeypatch.setattr(quality, "TMDB_KEY", "key")
        monkeypatch.setattr(quality, "_primary_audio_lang", lambda meta: "en")
        monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, mt: 1)
        monkeypatch.setattr(quality, "tmdb_get", lambda path: {"posters": [{"iso_639_1": None, "vote_average": 5}]})
        assert quality._language_mismatch({}, "movie") is False

    def test_mismatched_language_flags(self, monkeypatch):
        monkeypatch.setattr(quality, "TMDB_KEY", "key")
        monkeypatch.setattr(quality, "_primary_audio_lang", lambda meta: "en")
        monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, mt: 1)
        monkeypatch.setattr(quality, "tmdb_get", lambda path: {"posters": [{"iso_639_1": "ja", "vote_average": 9}]})
        assert quality._language_mismatch({}, "movie") is True

    def test_matched_language_does_not_flag(self, monkeypatch):
        monkeypatch.setattr(quality, "TMDB_KEY", "key")
        monkeypatch.setattr(quality, "_primary_audio_lang", lambda meta: "en")
        monkeypatch.setattr(quality, "tmdb_id_for_item", lambda meta, mt: 1)
        monkeypatch.setattr(quality, "tmdb_get", lambda path: {"posters": [{"iso_639_1": "en", "vote_average": 9}]})
        assert quality._language_mismatch({}, "movie") is False


class TestScanItemQuality:
    def test_placeholder_short_circuits(self, monkeypatch):
        monkeypatch.setattr(quality, "_language_mismatch", lambda meta, mt: True)
        assert quality.scan_item_quality({}, "movie", PLACEHOLDER_BYTES) == ["placeholder"]

    def test_low_res_flagged(self, monkeypatch):
        monkeypatch.setattr(quality, "_language_mismatch", lambda meta, mt: False)
        assert quality.scan_item_quality({}, "movie", LOW_RES_BYTES) == ["low_res"]

    def test_good_poster_no_flags(self, monkeypatch):
        monkeypatch.setattr(quality, "_language_mismatch", lambda meta, mt: False)
        assert quality.scan_item_quality({}, "movie", GOOD_BYTES) == []

    def test_language_mismatch_flagged_alongside_low_res(self, monkeypatch):
        monkeypatch.setattr(quality, "_language_mismatch", lambda meta, mt: True)
        assert quality.scan_item_quality({}, "movie", LOW_RES_BYTES) == ["low_res", "language_mismatch"]
