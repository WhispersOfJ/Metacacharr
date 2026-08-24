"""Tests for scripts/checkrr-badfiles-report.py.

The script's whole value is telling genuinely dead media apart from files
checkrr flags but which are fine, so the verification classifier gets the
bulk of the coverage. The regression case that motivated the script is
`test_zeroed_header_is_dead` paired with `test_disc_image_is_not_dead`:
before this, both landed in badfiles.csv as the same "unknown" reason.
"""
import csv
import importlib.util
import os
import sys

import pytest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "scripts", "checkrr-badfiles-report.py")

spec = importlib.util.spec_from_file_location("checkrr_badfiles_report", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["checkrr_badfiles_report"] = mod
spec.loader.exec_module(mod)


MKV_MAGIC = b"\x1a\x45\xdf\xa3"


@pytest.fixture
def fake_library(tmp_path, monkeypatch):
    """Point the script's repo root at a throwaway tree with media/ dirs."""
    for sub in ("media/movies", "media/shows", "media/anime-movies", "media/anime-shows"):
        (tmp_path / sub).mkdir(parents=True)
    monkeypatch.setattr(mod, "REPO_ROOT", str(tmp_path))
    return tmp_path


def write(fake_library, rel, data):
    path = fake_library / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# --- verification ------------------------------------------------------

def test_zeroed_header_is_dead(fake_library):
    """The nzbdav gap-fill signature: articles gone, header replaced by 0x00."""
    write(fake_library, "media/shows/Show/S01E01.mkv", b"\x00" * 4096)
    status, reason = mod.verify_file("/data/shows/Show/S01E01.mkv")
    assert status == mod.STATUS_DEAD
    assert "zeroed header" in reason


def test_valid_mkv_is_healthy(fake_library):
    write(fake_library, "media/shows/Show/S01E02.mkv", MKV_MAGIC + b"\x93\x42\x82" * 20)
    status, _ = mod.verify_file("/data/shows/Show/S01E02.mkv")
    assert status == mod.STATUS_HEALTHY


def test_disc_image_is_not_dead(fake_library):
    """ffprobe cannot demux an .iso, so checkrr flags healthy ones every run."""
    write(fake_library, "media/movies/Film (2023)/Film - [BR-DISK].iso", b"\x00" * 4096)
    status, _ = mod.verify_file("/data/movies/Film (2023)/Film - [BR-DISK].iso")
    assert status == mod.STATUS_UNPROBEABLE


def test_subtitle_is_classified_non_media(fake_library):
    write(fake_library, "media/movies/Film (2023)/Film.en.srt", b"1\n00:00:01,000\n")
    status, _ = mod.verify_file("/data/movies/Film (2023)/Film.en.srt")
    assert status == mod.STATUS_NON_MEDIA


def test_wrong_magic_for_extension_is_dead(fake_library):
    """Non-zero garbage still is not a Matroska file."""
    write(fake_library, "media/shows/Show/S01E03.mkv", b"NOTMKV!!" + b"\xff" * 8)
    status, reason = mod.verify_file("/data/shows/Show/S01E03.mkv")
    assert status == mod.STATUS_DEAD
    assert "bad header" in reason


def test_mp4_signature_is_offset_by_four(fake_library):
    """mp4 carries a box size before the 'ftyp' marker."""
    write(fake_library, "media/movies/Film (2023)/Film.mp4",
          b"\x00\x00\x00\x20ftypisom" + b"\x00" * 8)
    status, _ = mod.verify_file("/data/movies/Film (2023)/Film.mp4")
    assert status == mod.STATUS_HEALTHY


def test_mp4_with_fully_zeroed_head_is_dead(fake_library):
    """A dead mp4 must not be excused by its legitimate leading zero bytes."""
    write(fake_library, "media/movies/Film (2023)/Dead.mp4", b"\x00" * 4096)
    status, reason = mod.verify_file("/data/movies/Film (2023)/Dead.mp4")
    assert status == mod.STATUS_DEAD
    assert "zeroed header" in reason


def test_empty_file_is_dead(fake_library):
    write(fake_library, "media/shows/Show/S01E04.mkv", b"")
    status, reason = mod.verify_file("/data/shows/Show/S01E04.mkv")
    assert status == mod.STATUS_DEAD
    assert reason == "empty file"


def test_broken_symlink_reports_missing(fake_library):
    target = fake_library / "media/shows/Show"
    target.mkdir(parents=True, exist_ok=True)
    link = target / "S01E05.mkv"
    link.symlink_to("/nonexistent/gone.mkv")
    status, _ = mod.verify_file("/data/shows/Show/S01E05.mkv")
    assert status == mod.STATUS_MISSING


def test_path_outside_known_libraries(fake_library):
    status, _ = mod.verify_file("/data/other/thing.mkv")
    assert status == mod.STATUS_UNKNOWN_EXT


# --- csv loading -------------------------------------------------------

def test_load_badfiles_deduplicates(tmp_path):
    """badfiles.csv is cumulative across runs and repeats paths."""
    p = tmp_path / "badfiles.csv"
    p.write_text("/data/movies/A.mkv,unknown\n"
                 "/data/movies/A.mkv,unknown\n"
                 "/data/shows/B.mkv,unknown\n")
    entries = mod.load_badfiles(str(p))
    assert set(entries) == {"/data/movies/A.mkv", "/data/shows/B.mkv"}


def test_load_badfiles_handles_commas_in_titles(tmp_path):
    """Real paths contain commas; the reason is always the last field."""
    p = tmp_path / "badfiles.csv"
    p.write_text('"/data/shows/Hello, World/S01E01.mkv",unknown\n')
    entries = mod.load_badfiles(str(p))
    assert "/data/shows/Hello, World/S01E01.mkv" in entries


def test_load_badfiles_skips_blank_lines(tmp_path):
    p = tmp_path / "badfiles.csv"
    p.write_text("/data/movies/A.mkv,unknown\n\n   \n")
    assert len(mod.load_badfiles(str(p))) == 1


# --- path mapping ------------------------------------------------------

def test_container_to_host_maps_each_library(fake_library):
    cases = {
        "/data/movies/A.mkv": "media/movies/A.mkv",
        "/data/shows/B.mkv": "media/shows/B.mkv",
        "/data/anime-movies/C.mkv": "media/anime-movies/C.mkv",
        "/data/anime-shows/D.mkv": "media/anime-shows/D.mkv",
    }
    for container, rel in cases.items():
        assert mod.container_to_host(container) == os.path.join(str(fake_library), rel)


def test_container_to_host_rejects_unknown_prefix():
    assert mod.container_to_host("/data/nope/A.mkv") is None


def test_library_for_routes_anime_to_its_own_instance():
    assert mod.library_for("/data/anime-shows/X.mkv")[1] == "sonarr_anime"
    assert mod.library_for("/data/anime-movies/X.mkv")[1] == "radarr_anime"
    assert mod.library_for("/data/shows/X.mkv")[1] == "sonarr"
    assert mod.library_for("/data/movies/X.mkv")[1] == "radarr"


# --- checkrr.yaml parsing ----------------------------------------------

CHECKRR_YAML = """\
lang: "en-us"
checkrr:
  checkpath:
    - "/data/movies/"
  cron: "@daily"
arr:
  radarr:
    process: false
    service: radarr
    address: radarr
    apikey: "abc123"
    port: 7878
    mappings:
      "/data/movies/": "/data/movies/"
  sonarr_anime:
    process: false
    service: sonarr
    address: sonarr-anime
    apikey: "def456"
    port: 8989
    mappings:
      "/data/anime-shows/": "/data/anime-shows/"
webserver:
  port: 8585
"""


def test_parse_checkrr_yaml_extracts_arrs(tmp_path):
    p = tmp_path / "checkrr.yaml"
    p.write_text(CHECKRR_YAML)
    arrs = mod.parse_checkrr_yaml(str(p))
    assert set(arrs) == {"radarr", "sonarr_anime"}
    assert arrs["radarr"]["apikey"] == "abc123"
    assert arrs["radarr"]["port"] == "7878"
    assert arrs["sonarr_anime"]["service"] == "sonarr"
    assert arrs["sonarr_anime"]["address"] == "sonarr-anime"


def test_parse_checkrr_yaml_keeps_mappings_separate(tmp_path):
    p = tmp_path / "checkrr.yaml"
    p.write_text(CHECKRR_YAML)
    arrs = mod.parse_checkrr_yaml(str(p))
    assert arrs["radarr"]["mappings"] == {"/data/movies/": "/data/movies/"}
    assert "/data/movies/" not in arrs["radarr"]


def test_parse_checkrr_yaml_ignores_non_arr_sections(tmp_path):
    p = tmp_path / "checkrr.yaml"
    p.write_text(CHECKRR_YAML)
    arrs = mod.parse_checkrr_yaml(str(p))
    assert "checkrr" not in arrs
    assert "webserver" not in arrs


# --- sonarr indexing ---------------------------------------------------

def test_build_sonarr_index_only_queries_matching_series(monkeypatch):
    """Querying every series would be thousands of needless round-trips."""
    calls = []

    def fake_get(arr, endpoint, timeout=180):
        calls.append(endpoint)
        if endpoint == "series":
            return [
                {"id": 1, "title": "Wanted", "year": 2020, "path": "/data/shows/Wanted"},
                {"id": 2, "title": "Ignored", "year": 2021, "path": "/data/shows/Ignored"},
            ]
        return [{
            "id": 99, "path": "/data/shows/Wanted/S01E01.mkv",
            "relativePath": "Season 1/S01E01.mkv",
            "quality": {"quality": {"name": "WEBDL-1080p"}},
        }]

    monkeypatch.setattr(mod, "arr_get", fake_get)
    index = mod.build_sonarr_index({}, ["/data/shows/Wanted/S01E01.mkv"])

    assert "episodefile?seriesId=1" in calls
    assert "episodefile?seriesId=2" not in calls
    assert index["/data/shows/Wanted/S01E01.mkv"]["title"] == "Wanted"
    assert index["/data/shows/Wanted/S01E01.mkv"]["file_id"] == 99


def test_build_sonarr_index_survives_one_series_failing(monkeypatch):
    def fake_get(arr, endpoint, timeout=180):
        if endpoint == "series":
            return [
                {"id": 1, "title": "Broken", "year": 2020, "path": "/data/shows/Broken"},
                {"id": 2, "title": "Fine", "year": 2021, "path": "/data/shows/Fine"},
            ]
        if endpoint == "episodefile?seriesId=1":
            raise TimeoutError("boom")
        return [{
            "id": 7, "path": "/data/shows/Fine/S01E01.mkv",
            "relativePath": "Season 1/S01E01.mkv",
            "quality": {"quality": {"name": "Bluray-1080p"}},
        }]

    monkeypatch.setattr(mod, "arr_get", fake_get)
    index = mod.build_sonarr_index(
        {}, ["/data/shows/Broken/S01E01.mkv", "/data/shows/Fine/S01E01.mkv"])

    assert "/data/shows/Fine/S01E01.mkv" in index
    assert "/data/shows/Broken/S01E01.mkv" not in index


def test_build_radarr_index_skips_movies_without_files(monkeypatch):
    def fake_get(arr, endpoint, timeout=180):
        return [
            {"id": 1, "title": "Has File", "year": 2020, "monitored": True,
             "movieFile": {"id": 10, "path": "/data/movies/A.mkv",
                           "quality": {"quality": {"name": "Remux-2160p"}}}},
            {"id": 2, "title": "No File", "year": 2021, "monitored": True},
        ]

    monkeypatch.setattr(mod, "arr_get", fake_get)
    index = mod.build_radarr_index({})
    assert list(index) == ["/data/movies/A.mkv"]
    assert index["/data/movies/A.mkv"]["quality"] == "Remux-2160p"


# --- end to end --------------------------------------------------------

def test_main_writes_report_and_excludes_healthy(fake_library, tmp_path, monkeypatch, capsys):
    write(fake_library, "media/movies/Dead (2020)/Dead.mkv", b"\x00" * 4096)
    write(fake_library, "media/movies/Fine (2021)/Fine.mkv", MKV_MAGIC + b"\x00" * 12)
    write(fake_library, "media/movies/Disc (2022)/Disc.iso", b"\x00" * 4096)

    badfiles = tmp_path / "badfiles.csv"
    badfiles.write_text(
        "/data/movies/Dead (2020)/Dead.mkv,unknown\n"
        "/data/movies/Fine (2021)/Fine.mkv,unknown\n"
        "/data/movies/Disc (2022)/Disc.iso,unknown\n")

    config = tmp_path / "checkrr.yaml"
    config.write_text(CHECKRR_YAML)

    def fake_get(arr, endpoint, timeout=180):
        return [{"id": 5, "title": "Dead", "year": 2020, "monitored": True,
                 "movieFile": {"id": 55, "path": "/data/movies/Dead (2020)/Dead.mkv",
                               "quality": {"quality": {"name": "Bluray-1080p"}}}}]

    monkeypatch.setattr(mod, "arr_get", fake_get)
    monkeypatch.setattr(mod, "resolve_host_port", lambda arr: "7878")
    out = tmp_path / "report.csv"
    rc = mod.main(["--csv", str(badfiles), "--config", str(config), "--out", str(out)])
    assert rc == 0

    rows = list(csv.DictReader(open(out)))
    assert len(rows) == 1, "only the genuinely dead file belongs in the report"
    assert rows[0]["path"] == "/data/movies/Dead (2020)/Dead.mkv"
    assert rows[0]["tracked"] == "yes"
    assert rows[0]["title"] == "Dead"
    assert rows[0]["file_id"] == "55"


def test_main_marks_untracked_dead_file_as_orphan(fake_library, tmp_path, monkeypatch):
    write(fake_library, "media/movies/Gone (2020)/Gone.mkv", b"\x00" * 4096)
    badfiles = tmp_path / "badfiles.csv"
    badfiles.write_text("/data/movies/Gone (2020)/Gone.mkv,unknown\n")
    config = tmp_path / "checkrr.yaml"
    config.write_text(CHECKRR_YAML)

    monkeypatch.setattr(mod, "arr_get", lambda *a, **k: [])
    monkeypatch.setattr(mod, "resolve_host_port", lambda arr: "7878")
    out = tmp_path / "report.csv"
    mod.main(["--csv", str(badfiles), "--config", str(config), "--out", str(out)])

    rows = list(csv.DictReader(open(out)))
    assert rows[0]["tracked"] == "no"
    assert rows[0]["title"] == ""


def test_unreachable_arr_is_undetermined_not_orphan(fake_library, tmp_path,
                                                    monkeypatch, capsys):
    """A connection fault must not be recorded as 'no arr tracks this file'.

    Regression: the anime instances 401'd on the first live run and all 85 of
    their files were reported as orphans, which read as a real finding.
    """
    write(fake_library, "media/movies/Dead (2020)/Dead.mkv", b"\x00" * 4096)
    badfiles = tmp_path / "badfiles.csv"
    badfiles.write_text("/data/movies/Dead (2020)/Dead.mkv,unknown\n")
    config = tmp_path / "checkrr.yaml"
    config.write_text(CHECKRR_YAML)

    def boom(*a, **k):
        raise TimeoutError("radarr down")

    monkeypatch.setattr(mod, "resolve_host_port", lambda arr: "7878")
    monkeypatch.setattr(mod, "arr_get", boom)
    out = tmp_path / "report.csv"
    mod.main(["--csv", str(badfiles), "--config", str(config), "--out", str(out)])

    rows = list(csv.DictReader(open(out)))
    assert len(rows) == 1
    assert rows[0]["tracked"] == "unknown"
    captured = capsys.readouterr()
    assert "unreachable" in captured.err
    assert "UNDETERMINED" in captured.out


def test_http_401_is_treated_as_unreachable(fake_library, tmp_path, monkeypatch, capsys):
    """The exact failure the wrong-port bug produced."""
    write(fake_library, "media/movies/Dead (2020)/Dead.mkv", b"\x00" * 4096)
    badfiles = tmp_path / "badfiles.csv"
    badfiles.write_text("/data/movies/Dead (2020)/Dead.mkv,unknown\n")
    config = tmp_path / "checkrr.yaml"
    config.write_text(CHECKRR_YAML)

    def unauthorized(*a, **k):
        raise mod.urllib.error.HTTPError("http://localhost:7878", 401,
                                         "Unauthorized", {}, None)

    monkeypatch.setattr(mod, "resolve_host_port", lambda arr: "7878")
    monkeypatch.setattr(mod, "arr_get", unauthorized)
    out = tmp_path / "report.csv"
    mod.main(["--csv", str(badfiles), "--config", str(config), "--out", str(out)])

    assert list(csv.DictReader(open(out)))[0]["tracked"] == "unknown"


# --- host port resolution ----------------------------------------------

def test_resolve_host_port_uses_published_port(monkeypatch):
    """radarr-anime is 7878 in the container but 7879 on the host."""
    def fake_run(cmd, **kwargs):
        assert cmd == ["docker", "port", "radarr-anime", "7878/tcp"]
        return type("R", (), {"stdout": "0.0.0.0:7879\n[::]:7879\n"})()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.resolve_host_port({"address": "radarr-anime", "port": "7878"}) == "7879"


def test_resolve_host_port_prefers_ipv4_over_ipv6_line(monkeypatch):
    def fake_run(cmd, **kwargs):
        return type("R", (), {"stdout": "[::]:8990\n0.0.0.0:8990\n"})()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.resolve_host_port({"address": "sonarr-anime", "port": "8989"}) == "8990"


def test_resolve_host_port_falls_back_when_docker_missing(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    assert mod.resolve_host_port({"address": "radarr", "port": "7878"}) == "7878"


def test_arr_get_uses_resolved_host_port(monkeypatch):
    seen = {}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"[]"

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["key"] = req.get_header("X-api-key")
        return FakeResp()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mod.json, "load", lambda fh: [])
    mod.arr_get({"port": "8989", "_host_port": "8990", "apikey": "anime789"}, "series")

    assert "localhost:8990" in seen["url"], "must not hit the general instance"
    assert seen["key"] == "anime789"


ARRS = {
    "radarr": {"port": "7878", "apikey": "abc123", "service": "radarr"},
    "sonarr": {"port": "8989", "apikey": "def456", "service": "sonarr"},
}


def test_emit_commands_does_not_execute_anything(monkeypatch, capsys):
    """The remediation path must stay print-only in this stack."""
    ran = []
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: ran.append(a))
    mod.emit_commands([{
        "arr": "radarr", "title": "Dead", "year": 2020, "quality": "Bluray-1080p",
        "detail": "", "arr_id": 5, "file_id": 55,
    }], ARRS)
    out = capsys.readouterr().out
    assert "moviefile/55" in out
    assert "nothing below has been executed" in out
    assert ran == []


def test_emit_commands_deletes_then_searches_for_movie(capsys):
    mod.emit_commands([{
        "arr": "radarr", "title": "Dead", "year": 2020, "quality": "Bluray-1080p",
        "detail": "", "arr_id": 5, "file_id": 55,
    }], ARRS)
    out = capsys.readouterr().out
    delete_at = out.index("-X DELETE")
    search_at = out.index("MoviesSearch")
    assert delete_at < search_at, "the file record must be dropped before searching"
    assert '"movieIds":[5]' in out
    assert "localhost:7878" in out


def test_emit_commands_issues_one_search_per_series(capsys):
    """40 dead episodes in one series must not queue 40 identical searches."""
    rows = [{
        "arr": "sonarr", "title": "Show", "year": 2020, "quality": "WEBDL-1080p",
        "detail": f"Season 1/S01E{n:02d}.mkv", "arr_id": 9, "file_id": 100 + n,
    } for n in range(1, 5)]
    mod.emit_commands(rows, ARRS)
    out = capsys.readouterr().out
    assert out.count("SeriesSearch") == 1
    assert out.count("-X DELETE") == 4
    assert '"seriesId":9' in out


def test_emit_commands_separates_anime_instances(capsys):
    arrs = dict(ARRS)
    arrs["sonarr_anime"] = {"port": "8989", "apikey": "anime789", "service": "sonarr"}
    rows = [
        {"arr": "sonarr", "title": "A", "year": 2020, "quality": "q",
         "detail": "d", "arr_id": 1, "file_id": 11},
        {"arr": "sonarr_anime", "title": "B", "year": 2021, "quality": "q",
         "detail": "d", "arr_id": 2, "file_id": 22},
    ]
    mod.emit_commands(rows, arrs)
    out = capsys.readouterr().out
    assert "def456" in out and "anime789" in out
    assert out.count("SeriesSearch") == 2


def test_emit_commands_skips_rows_without_a_file_id(capsys):
    """An orphan has nothing to delete, so it must not produce a command."""
    mod.emit_commands([{
        "arr": "radarr", "title": "Orphan", "year": 2020, "quality": "",
        "detail": "", "arr_id": "", "file_id": "",
    }], ARRS)
    out = capsys.readouterr().out
    assert "-X DELETE" not in out
    assert "MoviesSearch" not in out
