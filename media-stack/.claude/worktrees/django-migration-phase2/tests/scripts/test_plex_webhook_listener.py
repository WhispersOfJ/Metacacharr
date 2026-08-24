import json
import urllib.error
from io import BytesIO


def _drain(mod):
    """Empty the module's shared post_queue between tests (module-scoped fixture)."""
    items = []
    while not mod.post_queue.empty():
        items.append(mod.post_queue.get_nowait())
    return items


def test_env_get_missing_file(plex_webhook_listener, tmp_path, monkeypatch):
    monkeypatch.setattr(plex_webhook_listener, "STACK_DIR", tmp_path)
    assert plex_webhook_listener.env_get("SOME_KEY") is None


def test_env_get_found_key(plex_webhook_listener, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("PLEX_TOKEN=abc123\n")
    monkeypatch.setattr(plex_webhook_listener, "STACK_DIR", tmp_path)
    assert plex_webhook_listener.env_get("PLEX_TOKEN") == "abc123"


def test_build_multipart_contains_payload_and_file(plex_webhook_listener):
    content_type, body = plex_webhook_listener.build_multipart(
        {"embeds": [{"title": "x"}]},
        [("files[0]", "poster.jpg", "image/jpeg", b"\xff\xd8\xff")],
    )
    assert content_type.startswith("multipart/form-data; boundary=")
    boundary = content_type.split("boundary=")[1]
    assert boundary.encode() in body
    assert b'name="payload_json"' in body
    assert b'filename="poster.jpg"' in body
    assert b"\xff\xd8\xff" in body
    assert body.rstrip().endswith(f"--{boundary}--".encode())


def test_parse_multipart_non_multipart_returns_empty(plex_webhook_listener):
    fields, thumb = plex_webhook_listener.parse_multipart("application/json", b'{"event":"library.new"}')
    assert fields == {}
    assert thumb is None


def test_parse_multipart_payload_only(plex_webhook_listener):
    content_type, body = plex_webhook_listener.build_multipart({"event": "library.new"}, [])
    fields, thumb = plex_webhook_listener.parse_multipart(content_type, body)
    assert json.loads(fields["payload_json"]) == {"event": "library.new"}
    assert thumb is None


def test_parse_multipart_extracts_thumb_file(plex_webhook_listener):
    boundary = "TESTBOUNDARY"
    content_type = f"multipart/form-data; boundary={boundary}"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="payload"\r\n\r\n'
        f'{{"event": "library.new"}}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="thumb"; filename="thumb.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + b"\xff\xd8\xff" + f"\r\n--{boundary}--\r\n".encode()
    fields, thumb = plex_webhook_listener.parse_multipart(content_type, body)
    assert json.loads(fields["payload"]) == {"event": "library.new"}
    assert thumb is not None
    data, content_type_out = thumb
    assert data == b"\xff\xd8\xff"
    assert content_type_out == "image/jpeg"


def test_plex_get_binary_returns_data_under_limit(plex_webhook_listener, monkeypatch):
    class _Resp(BytesIO):
        headers = type("H", (), {"get_content_type": lambda self: "image/png"})()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(plex_webhook_listener, "PLEX_URL", "http://plex.local:32400")
    monkeypatch.setattr(plex_webhook_listener, "PLEX_TOKEN", "tok")
    monkeypatch.setattr(plex_webhook_listener.urllib.request, "urlopen", lambda req, timeout=None: _Resp(b"imgdata"))
    data, content_type = plex_webhook_listener.plex_get_binary("/library/metadata/1/thumb")
    assert data == b"imgdata"
    assert content_type == "image/png"


def test_plex_get_binary_rejects_oversized_image(plex_webhook_listener, monkeypatch):
    class _Resp(BytesIO):
        headers = type("H", (), {"get_content_type": lambda self: "image/png"})()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    oversized = b"x" * (plex_webhook_listener.MAX_POSTER_BYTES + 1)
    monkeypatch.setattr(plex_webhook_listener.urllib.request, "urlopen", lambda req, timeout=None: _Resp(oversized))
    data, content_type = plex_webhook_listener.plex_get_binary("/library/metadata/1/thumb")
    assert data is None
    assert content_type is None


def test_handle_library_new_movie_label(plex_webhook_listener, monkeypatch):
    monkeypatch.setattr(plex_webhook_listener, "PLEX_URL", "")
    monkeypatch.setattr(plex_webhook_listener, "PLEX_TOKEN", "")
    _drain(plex_webhook_listener)
    payload = {"Metadata": {"title": "Some Movie", "year": 2024, "librarySectionTitle": "Movies"}}
    plex_webhook_listener.handle_library_new(payload, None)
    embed, image, label = plex_webhook_listener.post_queue.get_nowait()
    assert label == "Some Movie (2024)"
    assert embed["title"] == "Some Movie (2024)"
    assert embed["footer"]["text"] == "Added to Movies"
    assert image is None


def test_handle_library_new_episode_label_includes_show(plex_webhook_listener, monkeypatch):
    monkeypatch.setattr(plex_webhook_listener, "PLEX_URL", "")
    monkeypatch.setattr(plex_webhook_listener, "PLEX_TOKEN", "")
    _drain(plex_webhook_listener)
    payload = {"Metadata": {
        "title": "Pilot", "grandparentTitle": "Some Show",
        "librarySectionTitle": "TV Shows",
    }}
    plex_webhook_listener.handle_library_new(payload, None)
    embed, image, label = plex_webhook_listener.post_queue.get_nowait()
    assert label == "Some Show — Pilot"


def test_handle_library_new_summary_truncated(plex_webhook_listener, monkeypatch):
    monkeypatch.setattr(plex_webhook_listener, "PLEX_URL", "")
    monkeypatch.setattr(plex_webhook_listener, "PLEX_TOKEN", "")
    _drain(plex_webhook_listener)
    long_summary = "a" * 500
    payload = {"Metadata": {"title": "Long Movie", "summary": long_summary}}
    plex_webhook_listener.handle_library_new(payload, None)
    embed, image, label = plex_webhook_listener.post_queue.get_nowait()
    assert len(embed["description"]) == plex_webhook_listener.SUMMARY_LIMIT
    assert embed["description"].endswith("…")


def test_handle_library_new_uses_attached_thumb_without_fetch(plex_webhook_listener, monkeypatch):
    def _boom(path):
        raise AssertionError("should not fetch when a thumb was already attached")

    monkeypatch.setattr(plex_webhook_listener, "plex_get_binary", _boom)
    monkeypatch.setattr(plex_webhook_listener, "PLEX_URL", "http://plex.local:32400")
    monkeypatch.setattr(plex_webhook_listener, "PLEX_TOKEN", "tok")
    _drain(plex_webhook_listener)
    payload = {"Metadata": {"title": "Movie", "thumb": "/library/metadata/1/thumb"}}
    plex_webhook_listener.handle_library_new(payload, (b"bytes", "image/jpeg"))
    embed, image, label = plex_webhook_listener.post_queue.get_nowait()
    assert image == (b"bytes", "image/jpeg")


def test_handle_library_new_fetch_failure_leaves_image_none(plex_webhook_listener, monkeypatch):
    def _raise(path):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(plex_webhook_listener, "plex_get_binary", _raise)
    monkeypatch.setattr(plex_webhook_listener, "PLEX_URL", "http://plex.local:32400")
    monkeypatch.setattr(plex_webhook_listener, "PLEX_TOKEN", "tok")
    _drain(plex_webhook_listener)
    payload = {"Metadata": {"title": "Movie", "thumb": "/library/metadata/1/thumb"}}
    plex_webhook_listener.handle_library_new(payload, None)
    embed, image, label = plex_webhook_listener.post_queue.get_nowait()
    assert image is None


def test_post_discord_retries_once_on_429(plex_webhook_listener, monkeypatch):
    calls = {"n": 0}

    def _once(embed, image):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError("url", 429, "rate limited", {"Retry-After": "0"}, BytesIO(b""))

    monkeypatch.setattr(plex_webhook_listener, "post_discord_once", _once)
    monkeypatch.setattr(plex_webhook_listener.time, "sleep", lambda s: None)
    plex_webhook_listener.post_discord({"title": "x"}, None, "label")
    assert calls["n"] == 2


def test_post_discord_non_429_http_error_does_not_retry(plex_webhook_listener, monkeypatch, capsys):
    calls = {"n": 0}

    def _once(embed, image):
        calls["n"] += 1
        raise urllib.error.HTTPError("url", 500, "server error", {}, BytesIO(b""))

    monkeypatch.setattr(plex_webhook_listener, "post_discord_once", _once)
    plex_webhook_listener.post_discord({"title": "x"}, None, "label")
    assert calls["n"] == 1
    assert "discord post failed" in capsys.readouterr().err


def test_post_discord_once_json_only_when_no_image(plex_webhook_listener, monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=None):
        captured["content_type"] = req.headers.get("Content-type") or req.headers.get("Content-Type")
        captured["body"] = req.data
        return _Resp()

    monkeypatch.setattr(plex_webhook_listener, "DISCORD_WEBHOOK_URL", "http://discord.example/webhook")
    monkeypatch.setattr(plex_webhook_listener.urllib.request, "urlopen", _urlopen)
    embed = {"title": "x"}
    plex_webhook_listener.post_discord_once(embed, None)
    assert captured["content_type"] == "application/json"
    assert json.loads(captured["body"]) == {"embeds": [embed]}
