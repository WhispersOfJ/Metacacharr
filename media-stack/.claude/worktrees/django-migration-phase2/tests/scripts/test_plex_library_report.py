import json


def test_env_get_missing_file(plex_library_report, tmp_path, monkeypatch):
    monkeypatch.setattr(plex_library_report, "STACK_DIR", tmp_path)
    assert plex_library_report.env_get("SOME_KEY") is None


def test_env_get_found_key(plex_library_report, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("PLEX_TOKEN=abc123\n")
    monkeypatch.setattr(plex_library_report, "STACK_DIR", tmp_path)
    assert plex_library_report.env_get("PLEX_TOKEN") == "abc123"


def test_get_video_sections_filters_to_movie_and_show(plex_library_report, monkeypatch):
    monkeypatch.setattr(plex_library_report, "plex_get", lambda path: {"MediaContainer": {"Directory": [
        {"key": "1", "title": "Movies", "type": "movie"},
        {"key": "2", "title": "TV Shows", "type": "show"},
        {"key": "3", "title": "Music", "type": "artist"},
    ]}})
    assert plex_library_report.get_video_sections() == [("1", "Movies"), ("2", "TV Shows")]


def test_get_section_items_uses_guid_and_year(plex_library_report, monkeypatch):
    monkeypatch.setattr(plex_library_report, "plex_get", lambda path: {"MediaContainer": {"Metadata": [
        {"guid": "plex://movie/1", "title": "Movie A", "year": 2020, "ratingKey": "100"},
        {"guid": "plex://movie/2", "title": "Movie B", "ratingKey": "101"},
    ]}})
    items = plex_library_report.get_section_items("1")
    assert items["plex://movie/1"] == "Movie A (2020)"
    assert items["plex://movie/2"] == "Movie B"


def test_get_section_items_falls_back_to_rating_key_when_no_guid(plex_library_report, monkeypatch):
    monkeypatch.setattr(plex_library_report, "plex_get", lambda path: {"MediaContainer": {"Metadata": [
        {"title": "No Guid", "ratingKey": "999"},
    ]}})
    items = plex_library_report.get_section_items("1")
    assert items["ratingKey:999"] == "No Guid"


def test_label_of_plain_string(plex_library_report):
    assert plex_library_report.label_of("Movie A (2020)") == "Movie A (2020)"


def test_label_of_dict_shape(plex_library_report):
    assert plex_library_report.label_of({"title": "Movie A"}) == "Movie A"


def test_label_of_dict_missing_title_defaults_unknown(plex_library_report):
    assert plex_library_report.label_of({}) == "Unknown"


def test_truncate_list_under_limit(plex_library_report):
    result = plex_library_report.truncate_list(["b", "a"], limit=20)
    assert result == "• a\n• b"


def test_truncate_list_over_limit_shows_remainder_count(plex_library_report):
    items = [f"item{i}" for i in range(25)]
    result = plex_library_report.truncate_list(items, limit=20)
    assert "…and 5 more" in result
    assert result.count("• ") == 20


def test_load_previous_missing_file_returns_empty(plex_library_report, tmp_path, monkeypatch):
    monkeypatch.setattr(plex_library_report, "STATE_FILE", tmp_path / "snapshot.json")
    assert plex_library_report.load_previous() == {}


def test_save_and_load_previous_round_trip(plex_library_report, tmp_path, monkeypatch):
    state_file = tmp_path / "nested" / "snapshot.json"
    monkeypatch.setattr(plex_library_report, "STATE_FILE", state_file)
    snapshot = {"1": {"title": "Movies", "items": {"g1": "Movie A"}}}
    plex_library_report.save_current(snapshot)
    assert plex_library_report.load_previous() == snapshot


def test_post_discord_skips_when_unconfigured(plex_library_report, monkeypatch, capsys):
    monkeypatch.setattr(plex_library_report, "DISCORD_WEBHOOK_URL", None)

    def _boom(*a, **k):
        raise AssertionError("urlopen should not be called when webhook unconfigured")

    monkeypatch.setattr(plex_library_report.urllib.request, "urlopen", _boom)
    plex_library_report.post_discord({"title": "x"})
    assert "skipping notification" in capsys.readouterr().err


def test_post_discord_sends_with_user_agent(plex_library_report, monkeypatch):
    monkeypatch.setattr(plex_library_report, "DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=None):
        captured["headers"] = req.headers
        return _Resp()

    monkeypatch.setattr(plex_library_report.urllib.request, "urlopen", _urlopen)
    plex_library_report.post_discord({"title": "x"})
    assert "user-agent" in {k.lower() for k in captured["headers"]}


def test_main_missing_plex_config_returns_1(plex_library_report, monkeypatch):
    monkeypatch.setattr(plex_library_report, "PLEX_URL", "")
    monkeypatch.setattr(plex_library_report, "PLEX_TOKEN", "")
    assert plex_library_report.main() == 1


def test_main_baseline_run_establishes_snapshot_without_removed_fields(plex_library_report, tmp_path, monkeypatch):
    monkeypatch.setattr(plex_library_report, "PLEX_URL", "http://plex.local:32400")
    monkeypatch.setattr(plex_library_report, "PLEX_TOKEN", "tok")
    monkeypatch.setattr(plex_library_report, "STATE_FILE", tmp_path / "snapshot.json")
    monkeypatch.setattr(plex_library_report, "get_video_sections", lambda: [("1", "Movies")])
    monkeypatch.setattr(plex_library_report, "get_section_items", lambda key: {"g1": "Movie A"})
    posted = {}
    monkeypatch.setattr(plex_library_report, "post_discord", lambda embed: posted.update(embed))

    assert plex_library_report.main() == 0
    assert "Baseline established" in posted["description"]
    assert "fields" not in posted


def test_main_reports_removed_items(plex_library_report, tmp_path, monkeypatch):
    state_file = tmp_path / "snapshot.json"
    state_file.write_text(json.dumps({"1": {"title": "Movies", "items": {"g1": "Movie A", "g2": "Movie B"}}}))
    monkeypatch.setattr(plex_library_report, "PLEX_URL", "http://plex.local:32400")
    monkeypatch.setattr(plex_library_report, "PLEX_TOKEN", "tok")
    monkeypatch.setattr(plex_library_report, "STATE_FILE", state_file)
    monkeypatch.setattr(plex_library_report, "get_video_sections", lambda: [("1", "Movies")])
    monkeypatch.setattr(plex_library_report, "get_section_items", lambda key: {"g1": "Movie A"})
    posted = {}
    monkeypatch.setattr(plex_library_report, "post_discord", lambda embed: posted.update(embed))

    assert plex_library_report.main() == 0
    assert len(posted["fields"]) == 1
    assert "Movie B" in posted["fields"][0]["value"]
    assert "removed" in posted["fields"][0]["name"]


def test_main_no_removals_reports_quiet_run(plex_library_report, tmp_path, monkeypatch):
    state_file = tmp_path / "snapshot.json"
    state_file.write_text(json.dumps({"1": {"title": "Movies", "items": {"g1": "Movie A"}}}))
    monkeypatch.setattr(plex_library_report, "PLEX_URL", "http://plex.local:32400")
    monkeypatch.setattr(plex_library_report, "PLEX_TOKEN", "tok")
    monkeypatch.setattr(plex_library_report, "STATE_FILE", state_file)
    monkeypatch.setattr(plex_library_report, "get_video_sections", lambda: [("1", "Movies")])
    monkeypatch.setattr(plex_library_report, "get_section_items", lambda key: {"g1": "Movie A"})
    posted = {}
    monkeypatch.setattr(plex_library_report, "post_discord", lambda embed: posted.update(embed))

    assert plex_library_report.main() == 0
    assert posted["description"] == "No removals in the last 30 minutes."
