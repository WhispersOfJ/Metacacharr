import pytest


def test_mdblist_key_missing_exits(mdblist_toplists_import, monkeypatch):
    monkeypatch.delenv("MDBLIST_KEY", raising=False)
    with pytest.raises(SystemExit):
        mdblist_toplists_import.mdblist_key()


def test_mdblist_key_returns_env_value(mdblist_toplists_import, monkeypatch):
    monkeypatch.setenv("MDBLIST_KEY", "abc123")
    assert mdblist_toplists_import.mdblist_key() == "abc123"


def test_list_url_re_matches_two_segment_path(mdblist_toplists_import):
    m = mdblist_toplists_import.LIST_URL_RE.match("https://mdblist.com/lists/hdlists/latest-tv-shows")
    assert m is not None
    assert m.groups() == ("hdlists", "latest-tv-shows")


def test_list_url_re_rejects_three_segment_path(mdblist_toplists_import):
    assert mdblist_toplists_import.LIST_URL_RE.match(
        "https://mdblist.com/lists/official/movies/top-100"
    ) is None


def test_list_href_re_extracts_hrefs(mdblist_toplists_import):
    html = '<a href="/lists/hdlists/latest-tv-shows">Latest TV</a><a href="/lists/official">Official</a>'
    hrefs = mdblist_toplists_import.LIST_HREF_RE.findall(html)
    assert hrefs == ["/lists/hdlists/latest-tv-shows"]


def test_list_meta_returns_none_for_unrecognized_url(mdblist_toplists_import):
    assert mdblist_toplists_import.list_meta("https://mdblist.com/lists/official", "key") is None


def test_list_meta_returns_none_on_error_field(mdblist_toplists_import, monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"error": "list not found"}

    monkeypatch.setattr(mdblist_toplists_import.requests, "get", lambda *a, **k: FakeResp())
    result = mdblist_toplists_import.list_meta("https://mdblist.com/lists/hdlists/latest-tv-shows", "key")
    assert result is None


def test_list_meta_unwraps_single_element_list_response(mdblist_toplists_import, monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"name": "Latest TV Shows", "shows": 5}]

    monkeypatch.setattr(mdblist_toplists_import.requests, "get", lambda *a, **k: FakeResp())
    result = mdblist_toplists_import.list_meta("https://mdblist.com/lists/hdlists/latest-tv-shows", "key")
    assert result == {"name": "Latest TV Shows", "shows": 5}


def test_list_meta_returns_none_for_empty_list_response(mdblist_toplists_import, monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setattr(mdblist_toplists_import.requests, "get", lambda *a, **k: FakeResp())
    result = mdblist_toplists_import.list_meta("https://mdblist.com/lists/hdlists/latest-tv-shows", "key")
    assert result is None


def test_already_registered_matches_on_field_name_and_trailing_slash(mdblist_toplists_import):
    existing = [
        {"fields": [{"name": "url", "value": "https://mdblist.com/lists/hdlists/latest-tv-shows/"}]},
    ]
    assert mdblist_toplists_import.already_registered(
        existing, "url", "https://mdblist.com/lists/hdlists/latest-tv-shows"
    )


def test_already_registered_false_when_no_match(mdblist_toplists_import):
    existing = [{"fields": [{"name": "url", "value": "https://mdblist.com/lists/hdlists/other-list"}]}]
    assert not mdblist_toplists_import.already_registered(
        existing, "url", "https://mdblist.com/lists/hdlists/latest-tv-shows"
    )


def test_register_raises_runtime_error_with_detail_message(mdblist_toplists_import, monkeypatch):
    class FakeResp:
        status_code = 400
        text = "raw fallback text"

        def json(self):
            return {"detail": {"message": "duplicate name"}}

    monkeypatch.setattr(mdblist_toplists_import.requests, "post", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="duplicate name"):
        mdblist_toplists_import.register("radarr", "RadarrListImport", "name", "url", "https://example.com")


def test_register_falls_back_to_raw_text_when_json_invalid(mdblist_toplists_import, monkeypatch):
    class FakeResp:
        status_code = 500

        def json(self):
            raise ValueError("not json")

        text = "internal server error"

    monkeypatch.setattr(mdblist_toplists_import.requests, "post", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="internal server error"):
        mdblist_toplists_import.register("radarr", "RadarrListImport", "name", "url", "https://example.com")


def test_register_returns_message_on_success(mdblist_toplists_import, monkeypatch):
    class FakeResp:
        status_code = 200

        def json(self):
            return {"message": "added"}

    monkeypatch.setattr(mdblist_toplists_import.requests, "post", lambda *a, **k: FakeResp())
    result = mdblist_toplists_import.register("radarr", "RadarrListImport", "name", "url", "https://example.com")
    assert result == "added"
