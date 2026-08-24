"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/posters/router.py, ported from app.py. Covers auth gating,
source-configured gating, libraries listing, sync/review job lifecycle
(start/already-running/stream), and the single-item apply route.
"""
import json
import threading
import time
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="test-key", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


@pytest.mark.parametrize("method,path,json_body", [
    ("GET", "/api/posters/libraries", None),
    ("POST", "/api/posters/sync", {"library": "Movies"}),
    ("GET", "/api/posters/sync/stream", None),
    ("POST", "/api/posters/review", {"library": "Movies"}),
    ("GET", "/api/posters/review/stream", None),
    ("POST", "/api/posters/apply", {"rating_key": "1", "url": "http://x/p.jpg"}),
    ("GET", "/api/posters/gallery?library=Movies", None),
    ("GET", "/api/posters/thumb/1", None),
    ("POST", "/api/posters/scan", {"library": "Movies"}),
    ("GET", "/api/posters/scan/stream", None),
])
def test_routes_require_auth(cp_main_app, method, path, json_body):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path, json=json_body)
    assert resp.status_code == 401


def test_libraries_filters_to_movie_and_show(cp_main_app, monkeypatch):
    sections = [
        {"key": "1", "title": "Movies", "type": "movie"},
        {"key": "2", "title": "Music", "type": "artist"},
        {"key": "3", "title": "Shows", "type": "show"},
    ]
    monkeypatch.setattr("services.posters.router.plex_sections", lambda: sections)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/libraries", headers=headers)
    body = resp.json()
    assert [s["title"] for s in body] == ["Movies", "Shows"]


def test_sync_rejects_unconfigured_fanart_source(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.posters.router.FANART_KEY", None)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/posters/sync", json={"library": "Movies", "source": "fanart"}, headers=headers)
    assert resp.status_code == 503


def test_sync_starts_background_job_and_reports_already_running(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.posters.router.TMDB_KEY", "test-tmdb-key")
    started = threading.Event()

    def fake_run_poster_sync(library, dry_run, q, source):
        started.set()
        time.sleep(0.3)

    monkeypatch.setattr("services.posters.router.run_poster_sync", fake_run_poster_sync)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp1 = client.post("/api/posters/sync", json={"library": "Movies"}, headers=headers)
    assert resp1.status_code == 200
    assert started.wait(timeout=2)

    resp2 = client.post("/api/posters/sync", json={"library": "Movies"}, headers=headers)
    assert resp2.status_code == 409

    # Let the background job finish so the module-level POSTER_SYNC_STATE
    # is clean before the next test reuses this fresh cp_main_app import.
    time.sleep(0.3)


def test_sync_stream_404s_when_nothing_started(cp_main_app):
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/sync/stream", headers=headers)
    assert resp.status_code == 404


def test_review_starts_background_job_and_reports_already_running(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.posters.router.TMDB_KEY", "test-tmdb-key")
    started = threading.Event()

    def fake_run_poster_review(library, source, q):
        started.set()
        time.sleep(0.3)

    monkeypatch.setattr("services.posters.router.run_poster_review", fake_run_poster_review)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp1 = client.post("/api/posters/review", json={"library": "Movies", "source": "tmdb"}, headers=headers)
    assert resp1.status_code == 200
    assert started.wait(timeout=2)

    resp2 = client.post("/api/posters/review", json={"library": "Movies", "source": "tmdb"}, headers=headers)
    assert resp2.status_code == 409
    time.sleep(0.3)


def test_review_stream_404s_when_nothing_started(cp_main_app):
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/review/stream", headers=headers)
    assert resp.status_code == 404


def test_apply_uploads_poster_and_records_cooldown_timestamp(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.posters.state.POSTER_STATE_PATH", str(tmp_path / "state.json"))
    captured = {}

    def fake_post(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/posters/apply", json={"rating_key": "42", "url": "http://x/p.jpg"}, headers=headers)
    assert resp.status_code == 200
    assert captured["params"]["url"] == "http://x/p.jpg"
    assert "/library/metadata/42/posters" in captured["url"]

    from services.posters.state import load_poster_state
    assert "42" in load_poster_state()


def test_apply_502s_on_upload_failure(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.posters.state.POSTER_STATE_PATH", str(tmp_path / "state.json"))

    def fake_post(*a, **k):
        raise httpx.HTTPError("upload failed")

    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/posters/apply", json={"rating_key": "42", "url": "http://x/p.jpg"}, headers=headers)
    assert resp.status_code == 502


def _sections_page(cp_main_app, monkeypatch, sections):
    monkeypatch.setattr("services.posters.router.plex_sections", lambda: sections)


def test_gallery_returns_paginated_items_with_thumb_proxy_urls(cp_main_app, monkeypatch):
    _sections_page(cp_main_app, monkeypatch, [{"key": "1", "title": "Movies", "type": "movie"}])

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"MediaContainer": {
            "totalSize": 2,
            "Metadata": [
                {"ratingKey": "1", "title": "Alpha", "year": 2020, "thumb": "/library/metadata/1/thumb/123"},
                {"ratingKey": "2", "title": "Beta", "year": 2021},  # no thumb field at all
            ],
        }}
        return resp

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/gallery?library=Movies&offset=0&limit=60", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["thumbUrl"] == "/api/posters/thumb/1"
    assert body["items"][1]["thumbUrl"] is None


def test_gallery_404s_on_unknown_library(cp_main_app, monkeypatch):
    _sections_page(cp_main_app, monkeypatch, [{"key": "1", "title": "Movies", "type": "movie"}])
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/gallery?library=Nope", headers=headers)
    assert resp.status_code == 404


def test_gallery_rejects_limit_over_page_max(cp_main_app):
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/gallery?library=Movies&limit=9999", headers=headers)
    assert resp.status_code == 422


def test_thumb_streams_image_bytes_from_plex(cp_main_app, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert "/library/metadata/42/thumb" in url
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.content = b"fake-jpeg-bytes"
        resp.headers = {"content-type": "image/jpeg"}
        return resp

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/thumb/42", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b"fake-jpeg-bytes"
    assert resp.headers["content-type"] == "image/jpeg"


def test_thumb_404s_when_plex_fetch_fails(cp_main_app, monkeypatch):
    def fake_get(*a, **k):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/thumb/42", headers=headers)
    assert resp.status_code == 404


def test_scan_starts_background_job_and_reports_already_running(cp_main_app, monkeypatch):
    started = threading.Event()

    def fake_run_poster_scan(library, q):
        started.set()
        time.sleep(0.3)

    monkeypatch.setattr("services.posters.router.run_poster_scan", fake_run_poster_scan)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp1 = client.post("/api/posters/scan", json={"library": "Movies"}, headers=headers)
    assert resp1.status_code == 200
    assert started.wait(timeout=2)

    resp2 = client.post("/api/posters/scan", json={"library": "Movies"}, headers=headers)
    assert resp2.status_code == 409
    time.sleep(0.3)


def test_scan_stream_404s_when_nothing_started(cp_main_app):
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/posters/scan/stream", headers=headers)
    assert resp.status_code == 404


def test_run_poster_scan_emits_placeholder_flag_for_item_with_no_thumb(cp_main_app, monkeypatch):
    import queue as queue_mod

    from services.posters.router import run_poster_scan

    _sections_page(cp_main_app, monkeypatch, [{"key": "1", "title": "Movies", "type": "movie"}])

    def fake_get(url, headers=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"MediaContainer": {"Metadata": [
            {"ratingKey": "1", "title": "NoPoster", "year": 2020},  # no "thumb" key
        ]}}
        return resp

    monkeypatch.setattr(httpx, "get", fake_get)
    q = queue_mod.Queue()
    run_poster_scan("Movies", q)

    lines = [json.loads(q.get_nowait()) for _ in range(q.qsize())]
    item_lines = [line for line in lines if line["type"] == "item"]
    assert item_lines[0]["flags"] == ["no_poster"]
    assert lines[-1] == {"type": "done", "flagged": 1, "total": 1}
