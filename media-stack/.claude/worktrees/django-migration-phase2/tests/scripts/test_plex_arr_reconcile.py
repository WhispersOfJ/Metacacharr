"""Gate tests for the Plex/Arr reconcile.

These exist because of a real false positive on 2026-08-13. The first version
of the script decided visibility from Plex's SQLite `metadata_items.deleted_at`
and reported 75 broken items. All 75 were playable. A live plex restart and a
full library scan were run against a problem that did not exist.

The cause was multi-version episodes: Frieren S02E01 has a BluRay file and a
WEB-DL file on the same episode. Plex keeps superseded metadata_items rows that
still name a file path, so grouping by path and checking deleted_at makes every
second version look orphaned.

The fix was to define "in Plex" as "the API returns a Part for this path",
which is what a user actually sees. test_visibility_never_consults_deleted_at
is the regression guard: it fails if anyone reintroduces the DB shortcut.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/plex-arr-reconcile.py"


@pytest.fixture(scope="module")
def rec():
    spec = importlib.util.spec_from_file_location("_script_plex_arr_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_script_plex_arr_reconcile"] = module
    spec.loader.exec_module(module)
    return module


MKV = "/data/anime-shows/Frieren - Beyond Journey's End/Season 2/Frieren.S02E01.BluRay.mkv"
ISO = "/data/movies/Aswang (1994) {tmdb-133535}/Aswang (1994) - [DVD-R].iso"


def test_served_by_plex_is_ok(rec):
    assert rec.classify(MKV, served=True, on_disk=True) == "ok"


def test_the_2026_08_13_false_positive_stays_fixed(rec):
    """A second-version file: on disk, served by Plex, and carrying a
    deleted_at-flagged row in the DB. Must be ok. This is the exact shape of
    all 75 items the first version wrongly reported."""
    assert rec.classify(MKV, served=True, on_disk=True) == "ok"


def test_on_disk_but_not_served_needs_attention(rec):
    assert rec.classify(MKV, served=False, on_disk=True) == "missing_from_plex"


def test_arr_tracking_a_file_that_is_gone_is_an_arr_problem(rec):
    """Not a Plex fault, and it must not be reported as one."""
    assert rec.classify(MKV, served=False, on_disk=False) == "file_gone"


def test_disc_image_is_not_a_scan_failure(rec):
    assert rec.classify(ISO, served=False, on_disk=True) == "unsupported"


def test_unsupported_check_is_case_insensitive(rec):
    assert rec.classify(ISO.replace(".iso", ".ISO"), served=False,
                        on_disk=True) == "unsupported"


def test_a_missing_disc_image_is_file_gone_not_unsupported(rec):
    """Existence outranks container type - otherwise a deleted .iso is filed
    as 'Plex cannot index it', hiding a real Arr-side gap."""
    assert rec.classify(ISO, served=False, on_disk=False) == "file_gone"


def test_a_served_disc_image_is_still_ok(rec):
    """If Plex somehow serves it, the suffix rule must not override reality."""
    assert rec.classify(ISO, served=True, on_disk=True) == "ok"


def test_visibility_never_consults_deleted_at(rec):
    """The regression guard. classify() takes `served`, which comes from the
    API; if a future edit reaches for the DB flag again, this fails.

    Docstrings are stripped before the check - the prose deliberately names
    deleted_at to explain why it is not used, and a naive substring search on
    the raw source would flag that explanation as the offence.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(rec))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]

    assert "deleted_at" not in ast.unparse(tree), (
        "deleted_at is back in the executable logic - visibility must come "
        "from the Plex API, not the database flag. See this file's docstring.")
    assert "served" in inspect.signature(rec.classify).parameters


def test_the_regression_guard_can_actually_fail(rec):
    """A guard nobody has seen fail is not known to work. Same stripping
    logic, run against code that does use the flag."""
    import ast

    offender = ast.parse('def f(x):\n    """deleted_at is fine here."""\n'
                         '    return x.deleted_at is None\n')
    for node in ast.walk(offender):
        if isinstance(node, ast.FunctionDef) and node.body:
            node.body = node.body[1:]
    assert "deleted_at" in ast.unparse(offender)


def test_shows_use_allleaves_and_movies_use_all(rec):
    """/all stops at the series level for shows, so it returns no episode
    Parts at all - using it would report every episode as missing."""
    endpoints = {label: ep for label, _, ep in rec.LIBRARIES.values()}
    assert endpoints["Movies"] == "all"
    assert endpoints["Anime Movies"] == "all"
    assert endpoints["Shows"] == "allLeaves"
    assert endpoints["Anime Shows"] == "allLeaves"


@pytest.mark.parametrize("path,expected", [
    ("/data/movies/X (2020)/X.mkv", "Movies"),
    ("/data/anime-movies/Y (2021)/Y.mkv", "Anime Movies"),
    ("/data/shows/Z/Season 1/Z.mkv", "Shows"),
    ("/data/anime-shows/W/Season 1/W.mkv", "Anime Shows"),
    ("/mnt/somewhere/else.mkv", None),
])
def test_library_is_derived_from_the_path_not_the_arr_instance(rec, path, expected):
    """radarr-anime writing into /data/movies must be filed under Movies, or
    the per-library totals silently lie."""
    assert rec.library_of(path) == expected


def test_anime_movies_is_not_swallowed_by_the_movies_prefix(rec):
    assert rec.library_of("/data/anime-movies/A/A.mkv") == "Anime Movies"


def test_every_library_maps_to_a_distinct_plex_section(rec):
    sections = [sid for _, sid, _ in rec.LIBRARIES.values()]
    assert len(set(sections)) == len(sections)
