# Letterboxd Amplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Letterboxd integration into its own `services/letterboxd/` module and add six capabilities on top of it: rating-aware quality-profile mapping, scheduled diff-only sync, TV/Sonarr crossover for miscategorized titles, tag scraping into Radarr tags, a slug→TMDb dedup cache, and sync telemetry surfaced in the dashboard.

**Architecture:** All six features live behind FastAPI routes in a new `control-panel/services/letterboxd/` package (auto-mounted by `main.py`'s `_discover_routers()`), backed by three new SQLite tables via SQLAlchemy models (`letterboxd_tmdb_cache`, `letterboxd_tracked_list`, `letterboxd_sync_log`) in the existing `/data/control-panel.db`. Scheduling reuses the stack's existing pattern: a standalone `scripts/letterboxd-sync.py` calling the control-panel HTTP API, driven by a systemd user timer (same shape as `stack-poster-sync-movies.timer`) — no in-process scheduler. The existing Letterboxd routes currently living in `control-panel/services/radarr/router.py` are moved into the new package; nothing about their external HTTP contract (URL paths, request/response JSON shapes) changes, so no caller (the fish functions calling them today) needs to change for that part.

**Tech Stack:** FastAPI 0.141.1, httpx 0.28.1, SQLAlchemy 2.0.51 (no Alembic migrations in this codebase despite `alembic.ini` existing — tables are created via `Base.metadata.create_all()` at app startup, see `control-panel/core/db.py`), pytest with `unittest.mock.MagicMock`/`monkeypatch` for httpx mocking (no `respx` or `httpx_mock` dependency present — don't add one), fish 3.x for CLI, systemd user timers for scheduling.

## Global Constraints

- Every mutating route that automation (fish CLI / systemd script) calls unattended must use `Depends(current_user_or_service)`, not `Depends(current_user)`, and must carry a one-line comment next to the route naming the caller and date — this is the documented exception process in `core/security.py`'s `current_user_or_service` docstring. Every other mutating route (UI-only) uses `Depends(current_user)`.
- New DB tables follow the existing `models/*.py` pattern exactly: SQLAlchemy 2.0 `Mapped`/`mapped_column` style, one class per file, registered by import in `models/__init__.py`.
- Every new/changed route returns the existing envelope shape: `ok(message, **extra)` → `{"ok": true, "message": ..., "time": ..., **extra}`, or raises via `fail(message, status_code)` → `HTTPException(status_code, detail={"ok": false, "message": ..., "time": ...})`. Never return a bare dict or a different shape — the fish `__stack_api` helper and the frontend both parse this exact envelope.
- No new secrets. `TMDB_KEY` already exists as an env var (`os.environ.get("TMDB_KEY")`, used in `control-panel/app.py` and `services/posters/candidates.py`) but this plan does **not** use it — the Sonarr crossover (Task 6) uses Sonarr's own `/api/v3/series/lookup?term=` endpoint instead, which needs no external API key at all.
- Letterboxd scraping stays within the site's `robots.txt` allowances already encoded in `LETTERBOXD_DISALLOWED_RE`/`LETTERBOXD_GRID_RE` — do not widen the allowed URL shapes without re-checking `https://letterboxd.com/robots.txt` live first.
- Outbound Letterboxd fetches keep the existing `time.sleep(0.2)` pacing between requests and the existing 10-page/720-item hard cap. Do not remove either.
- Test fixture: use `cp_main_app` (not `cp_app` — that fixture is for the retired `app.py`, which is no longer mounted by the Dockerfile's `CMD`). `cp_main_app` gives a fresh `main.py` import against a throwaway sqlite file per test.

---

## File Structure

```
control-panel/
  models/
    letterboxd_cache.py        # NEW - slug -> tmdb_id/media_type cache (Task 1)
    letterboxd_tracked_list.py # NEW - registered lists for scheduled sync (Task 1)
    letterboxd_sync_log.py     # NEW - one row per sync run, for telemetry (Task 1)
    __init__.py                # MODIFIED - register the 3 new models
  services/
    letterboxd/                # NEW package - all Letterboxd logic lives here now
      __init__.py               # NEW - empty, matches every other services/<name>/
      scraping.py                # NEW - page fetch, regexes, rating/tag/title parsing (Task 2)
      cache.py                   # NEW - slug->tmdb_id cache read/write helpers (Task 3)
      router.py                  # NEW - all HTTP routes (Tasks 2, 4, 5, 6, 8)
      sync.py                    # NEW - diff-only sync + telemetry logic, called by router (Tasks 7, 8)
    radarr/
      router.py                  # MODIFIED - Letterboxd routes removed (moved to services/letterboxd/router.py); `exclude` route stays
    sonarr/
      router.py                  # unchanged - reuses core/arr_client.sonarr_add_series, already present
  core/
    arr_client.py               # MODIFIED - add radarr_ensure_tags() (Task 5)
  tests/  (repo-root tests/, not control-panel/tests/ - see Global Constraints)
scripts/
  letterboxd-sync.py            # NEW - systemd-invoked diff sync client (Task 9)
systemd/
  stack-letterboxd-sync.service # NEW (Task 9)
  stack-letterboxd-sync.timer   # NEW (Task 9)
fish-functions/
  stack-letterboxd-radarr.fish            # MODIFIED - path only, behavior unchanged (Task 2)
  stack-letterboxd-radarr-list.fish       # MODIFIED - add --tags-as-radarr-tags, --rating-quality-map flags (Tasks 4, 5)
  stack-letterboxd-radarr-track.fish      # NEW (Task 8)
  stack-letterboxd-radarr-untrack.fish    # NEW (Task 8)
  stack-letterboxd-radarr-tracked.fish    # NEW (Task 8)
  stack-letterboxd-radarr-history.fish    # NEW (Task 10)
tests/
  conftest.py                             # MODIFIED - fix broken RADARR_ANIME_API_KEY gap (Task 0)
  control_panel/
    test_letterboxd_router.py             # NEW (Tasks 2, 4, 5, 6, 8)
    test_letterboxd_cache.py              # NEW (Task 3)
    test_letterboxd_sync.py               # NEW (Task 7)
  scripts/
    test_letterboxd_sync_script.py        # NEW (Task 9)
```

---

### Task 0: Fix the broken `cp_main_app` test fixture (prerequisite)

This blocks every other task in this plan — confirmed live by running the existing suite before writing anything:

```
$ /tmp/venv/bin/python3 -m pytest tests/control_panel/test_radarr_sonarr_prowlarr_bazarr_router.py -x -q
...
E   KeyError: 'RADARR_ANIME_API_KEY'
control-panel/core/arr_client.py:43: KeyError
```

`core/arr_client.py`'s `ARR_APPS` dict indexes `os.environ["RADARR_ANIME_API_KEY"]` directly (added for the anime-library re-enablement work, commit history around 2026-08-06), but `tests/conftest.py`'s `cp_main_app` fixture was never updated to set it, so importing `main` (which transitively imports `core.arr_client`) KeyErrors in every test using that fixture. This is a real, currently-broken gate test, unrelated to Letterboxd but blocking this whole plan's test suite.

**Files:**
- Modify: `tests/conftest.py:79-81`

**Interfaces:**
- Produces: a working `cp_main_app` fixture every later task's tests depend on. No new interface, just an unblocked existing one.

- [ ] **Step 1: Reproduce the failure**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_radarr_sonarr_prowlarr_bazarr_router.py -x -q`
Expected: FAIL with `KeyError: 'RADARR_ANIME_API_KEY'`

- [ ] **Step 2: Add the missing env var to the fixture**

In `tests/conftest.py`, right after line 80 (`monkeypatch.setenv("PROWLARR_API_KEY", "test-prowlarr-key")`), add:

```python
    monkeypatch.setenv("RADARR_ANIME_API_KEY", "test-radarr-anime-key")
```

- [ ] **Step 3: Run the full existing control-panel suite to confirm the fix**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/ tests/scripts/ -q`
Expected: PASS (all previously-collected tests now run instead of erroring at fixture setup)

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "fix: add missing RADARR_ANIME_API_KEY to cp_main_app test fixture"
```

---

### Task 1: New SQLAlchemy models

**Files:**
- Create: `control-panel/models/letterboxd_cache.py`
- Create: `control-panel/models/letterboxd_tracked_list.py`
- Create: `control-panel/models/letterboxd_sync_log.py`
- Modify: `control-panel/models/__init__.py`
- Test: `tests/control_panel/test_letterboxd_models.py`

**Interfaces:**
- Produces: `LetterboxdTmdbCache` (columns: `slug` str PK, `tmdb_id` int nullable, `media_type` str default `"movie"`, `cached_at` datetime), `LetterboxdTrackedList` (columns: `id` int PK, `url` str unique, `label` str nullable, `root_folder` str nullable, `quality_profile` str nullable, `rating_quality_map_json` str nullable, `tags_as_radarr_tags` bool default False, `created_at` datetime, `last_synced_at` datetime nullable), `LetterboxdSyncLog` (columns: `id` int PK, `list_url` str, `run_at` datetime, `matched` int, `unmatched` int, `added` int, `already` int, `failed` int, `tv_crossover` int, `error_detail` str nullable).

- [ ] **Step 1: Write the failing test**

```python
# tests/control_panel/test_letterboxd_models.py
def test_letterboxd_tables_are_created(cp_main_app):
    from models.letterboxd_cache import LetterboxdTmdbCache
    from models.letterboxd_tracked_list import LetterboxdTrackedList
    from models.letterboxd_sync_log import LetterboxdSyncLog

    db = cp_main_app.SessionLocal()
    try:
        db.add(LetterboxdTmdbCache(slug="the-matrix", tmdb_id=603, media_type="movie"))
        db.add(LetterboxdTrackedList(url="https://letterboxd.com/bear/watchlist/", label="Bear's watchlist"))
        db.add(LetterboxdSyncLog(list_url="https://letterboxd.com/bear/watchlist/", matched=10, unmatched=1,
                                  added=5, already=4, failed=0, tv_crossover=1))
        db.commit()

        cache_row = db.query(LetterboxdTmdbCache).filter_by(slug="the-matrix").one()
        assert cache_row.tmdb_id == 603
        tracked_row = db.query(LetterboxdTrackedList).filter_by(url="https://letterboxd.com/bear/watchlist/").one()
        assert tracked_row.label == "Bear's watchlist"
        log_row = db.query(LetterboxdSyncLog).filter_by(list_url="https://letterboxd.com/bear/watchlist/").one()
        assert log_row.added == 5
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_models.py -x -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'models.letterboxd_cache'`

- [ ] **Step 3: Write the models**

```python
# control-panel/models/letterboxd_cache.py
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class LetterboxdTmdbCache(Base):
    """slug -> TMDb id, so a re-scraped list/watchlist doesn't re-fetch
    every film's own Letterboxd page just to re-derive an id that never
    changes. tmdb_id is nullable: a slug with no TMDb match (unmatched at
    scrape time) is cached too, so re-runs don't keep re-fetching known
    dead ends - see services/letterboxd/cache.py."""

    __tablename__ = "letterboxd_tmdb_cache"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str] = mapped_column(String, nullable=False, default="movie")
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# control-panel/models/letterboxd_tracked_list.py
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class LetterboxdTrackedList(Base):
    """A Letterboxd list/watchlist registered for the nightly diff-only
    sync (services/letterboxd/sync.py, scripts/letterboxd-sync.py). Row
    presence IS the registration - there's no separate enabled flag,
    untrack deletes the row."""

    __tablename__ = "letterboxd_tracked_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    root_folder: Mapped[str | None] = mapped_column(String, nullable=True)
    quality_profile: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSON-encoded dict[str, str] of {"letterboxd rating 1-10": "radarr quality profile name"} -
    # same JSON-in-a-string-column pattern as models/setting.py's value_json.
    rating_quality_map_json: Mapped[str | None] = mapped_column(String, nullable=True)
    tags_as_radarr_tags: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

```python
# control-panel/models/letterboxd_sync_log.py
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.db import Base


class LetterboxdSyncLog(Base):
    """One row per add-from-letterboxd-list (or scheduled sync-tick) run -
    surfaced by GET /api/arr/letterboxd/history so a silently degrading
    list (404s, zero match rate) is visible instead of only living in
    container logs."""

    __tablename__ = "letterboxd_sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_url: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmatched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    already: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tv_crossover: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail: Mapped[str | None] = mapped_column(String, nullable=True)
```

Update `control-panel/models/__init__.py` to append:

```python
from models.letterboxd_cache import LetterboxdTmdbCache  # noqa: F401
from models.letterboxd_tracked_list import LetterboxdTrackedList  # noqa: F401
from models.letterboxd_sync_log import LetterboxdSyncLog  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_models.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add control-panel/models/letterboxd_cache.py control-panel/models/letterboxd_tracked_list.py \
        control-panel/models/letterboxd_sync_log.py control-panel/models/__init__.py \
        tests/control_panel/test_letterboxd_models.py
git commit -m "feat: add Letterboxd cache, tracked-list, and sync-log models"
```

---

### Task 2: Extract Letterboxd scraping + move existing routes into `services/letterboxd/`

Moves `LETTERBOXD_TMDB_RE`, `LETTERBOXD_ITEM_SLUG_RE`, `LETTERBOXD_LIST_PAGE_RE`, `LETTERBOXD_DISALLOWED_RE`, `LETTERBOXD_GRID_RE`, `_LETTERBOXD_HEADERS`, `_letterboxd_page`, `_letterboxd_page_or_none` out of `control-panel/services/radarr/router.py:23-66` into a new `control-panel/services/letterboxd/scraping.py`, and moves the two existing routes (`POST /api/arr/radarr/add-from-letterboxd`, `POST /api/arr/radarr/add-from-letterboxd-list`) into a new `control-panel/services/letterboxd/router.py`, unchanged in behavior. The `exclude` route (`arr_radarr_exclude`) stays in `services/radarr/router.py` — it isn't Letterboxd-specific.

**Files:**
- Create: `control-panel/services/letterboxd/__init__.py` (empty file)
- Create: `control-panel/services/letterboxd/scraping.py`
- Create: `control-panel/services/letterboxd/router.py`
- Modify: `control-panel/services/radarr/router.py` (remove lines 1-233, keep the `ExcludeRequest`/`arr_radarr_exclude` block and its imports)
- Test: `tests/control_panel/test_letterboxd_router.py`

**Interfaces:**
- Consumes: `core.arr_client.ARR_APPS`, `core.arr_client.radarr_root_folder_and_profile`, `core.arr_client.radarr_add_movie`, `core.responses.ok`/`fail`, `core.security.current_user_or_service`.
- Produces: `services.letterboxd.scraping.fetch_page(url: str) -> str`, `services.letterboxd.scraping.fetch_page_or_none(url: str) -> str | None`, `services.letterboxd.scraping.LETTERBOXD_TMDB_RE`, `LETTERBOXD_ITEM_SLUG_RE`, `LETTERBOXD_LIST_PAGE_RE`, `LETTERBOXD_DISALLOWED_RE`, `LETTERBOXD_GRID_RE` (module-level compiled regexes, same patterns as before — later tasks import these). `services.letterboxd.router.router` (an `APIRouter`, auto-mounted by `main.py`).

- [ ] **Step 1: Write the failing test (routes exist at the new location, old location no longer serves them)**

```python
# tests/control_panel/test_letterboxd_router.py
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient


def _login(client, main_module, password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200


def _json_response(payload, status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


def test_add_from_letterboxd_route_lives_under_services_letterboxd(cp_main_app, monkeypatch):
    letterboxd_html = '<html><meta property="og:title" content="The Matrix (1999)"/>themoviedb.org/movie/603</html>'

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com" in url:
            return MagicMock(text=letterboxd_html, raise_for_status=MagicMock())
        if "/movie" in url and params and params.get("tmdbId") == 603:
            return _json_response([{"id": 99, "title": "The Matrix", "year": 1999}])
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/the-matrix/"})
    assert resp.status_code == 200
    assert resp.json()["alreadyAdded"] is True


def test_radarr_exclude_route_still_lives_in_radarr_router(cp_main_app, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        return _json_response({"id": 5, "title": "Some Movie", "year": 2020, "tmdbId": 111})

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        return _json_response({}, status_code=201)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/exclude", json={"movieId": 5})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py -x -q`
Expected: PASS for `test_radarr_exclude_route_still_lives_in_radarr_router` (unchanged route), FAIL for `test_add_from_letterboxd_route_lives_under_services_letterboxd` only in the sense that it currently passes too (route still exists in radarr/router.py) — this step is really a pre-refactor snapshot; the meaningful check is Step 4 after the move, confirming nothing broke.

- [ ] **Step 3: Create `scraping.py`**

```python
# control-panel/services/letterboxd/scraping.py
"""Letterboxd page-fetch + regex primitives, split out of
services/radarr/router.py (which owned add-from-letterboxd* before this
package existed) - every Letterboxd-touching route in this package imports
from here instead of redeclaring these.
"""
import re

import httpx

from core.responses import fail

# Letterboxd doesn't expose TMDb ids directly, but every matched film page
# links to its TMDb entry in the sidebar - regex is simpler and more stable
# than parsing Letterboxd's HTML structure.
LETTERBOXD_TMDB_RE = re.compile(r"themoviedb\.org/movie/(\d+)")
# List/watchlist grid pages carry each poster's slug in this attribute.
LETTERBOXD_ITEM_SLUG_RE = re.compile(r'data-item-slug="([^"]+)"')
LETTERBOXD_LIST_PAGE_RE = re.compile(r"/page/(\d+)/")
# og:title is present on every Letterboxd film page (confirmed live,
# 2026-08-06, against https://letterboxd.com/film/oppenheimer/) as
# `<meta property="og:title" content="Title (Year)">` - used as the
# TV-crossover fallback title/year source when a film has no TMDb movie
# match (see services/letterboxd/router.py's Sonarr fallback).
LETTERBOXD_OG_TITLE_RE = re.compile(r'property="og:title" content="([^"(]+?)\s*\((\d{4})\)"')
# Own-ratings marker, confirmed live 2026-08-06 against
# https://letterboxd.com/<user>/films/ - each poster's <li> contains, only
# when the page owner rated that film,
# `<span class="rating -micro -darker rated-N">` where N is 1-10 (half-star
# granularity: N/2 = star count). Absent entirely for an unrated film, so
# this must be matched per-item-segment, not as a flat list zipped
# positionally against LETTERBOXD_ITEM_SLUG_RE's matches - see
# scrape_slugs_with_ratings() below.
LETTERBOXD_RATING_RE = re.compile(r'rated-(\d+)"')
# Tag chip pattern on a user's own logged/reviewed film page
# (https://letterboxd.com/<user>/film/<slug>/) - Letterboxd's documented
# public markup (community scrapers: letterboxdpy, judahpaul16/gruvbox-*).
# NOT independently confirmed live in this session (the specific user/film
# pages fetched during research had no tags set) - Task 5's Step 1 must
# re-verify this against a live page known to carry tags before relying on
# it, and adjust the pattern if Letterboxd's markup has since changed.
LETTERBOXD_TAG_RE = re.compile(r'href="/[^/]+/tag/([^/"]+)/"[^>]*class="tag"')

# robots.txt's "User-agent: *" section disallows these sort/filter path
# segments specifically.
LETTERBOXD_DISALLOWED_RE = re.compile(
    r"/(by|on|tag|genre|country|language|decade|friends)/"
    r"|/popular/this/"
    r"|/films/year/"
    r"|/films/[^/]+/year/"
    r"|/films/[^/]+/size/large/"
)
LETTERBOXD_GRID_RE = re.compile(
    r"^https://letterboxd\.com/(?:[^/]+/(?:list/[^/]+|watchlist|films)|[a-z-]+/[^/]+|films/in/[^/]+|films)/?$"
)

_LETTERBOXD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_page(url: str) -> str:
    try:
        page = httpx.get(url, headers=_LETTERBOXD_HEADERS, timeout=15, follow_redirects=True)
        page.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't fetch {url}: {e}")
    return page.text


def fetch_page_or_none(url: str) -> str | None:
    try:
        page = httpx.get(url, headers=_LETTERBOXD_HEADERS, timeout=15, follow_redirects=True)
        page.raise_for_status()
    except httpx.HTTPError:
        return None
    return page.text


def scrape_slugs_with_ratings(page_html: str) -> list[tuple[str, int | None]]:
    """Returns [(slug, rating_or_None), ...] in document order. Splits on
    each data-item-slug occurrence so a rating (when present) is matched
    only within its own <li>'s segment, not positionally zipped against a
    separate flat rating list - a film with no rating has no rated-N
    marker at all, so a flat zip would misalign every item after it."""
    slug_positions = [(m.group(1), m.start()) for m in re.finditer(r'data-item-slug="([^"]+)"', page_html)]
    results = []
    seen = set()
    for i, (slug, start) in enumerate(slug_positions):
        if slug in seen:
            continue
        seen.add(slug)
        end = slug_positions[i + 1][1] if i + 1 < len(slug_positions) else len(page_html)
        segment = page_html[start:end]
        rating_match = LETTERBOXD_RATING_RE.search(segment)
        results.append((slug, int(rating_match.group(1)) if rating_match else None))
    return results


def scrape_title_year(film_page_html: str) -> tuple[str, int] | None:
    match = LETTERBOXD_OG_TITLE_RE.search(film_page_html)
    if not match:
        return None
    return match.group(1).strip(), int(match.group(2))


def scrape_tags(user_film_page_html: str) -> list[str]:
    return list(dict.fromkeys(LETTERBOXD_TAG_RE.findall(user_film_page_html)))
```

- [ ] **Step 4: Create `router.py` with the two moved routes**

```python
# control-panel/services/letterboxd/router.py
"""Letterboxd -> Radarr/Sonarr integration routes. Owns every
/api/arr/*letterboxd* and /api/arr/letterboxd/* route - the single-film
and list/watchlist/filmography/collection adds (originally in
services/radarr/router.py, moved here 2026-08-06 once this became a
first-class integration spanning both Radarr and Sonarr), plus the
dedup-cache, rating-quality-mapping, tag-scraping, TV-crossover,
tracked-list, and sync-history features layered on top in this same plan.
"""
import time

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.arr_client import ARR_APPS, radarr_add_movie, radarr_root_folder_and_profile
from core.responses import fail, ok
from core.security import current_user_or_service
from services.letterboxd.scraping import (
    LETTERBOXD_DISALLOWED_RE,
    LETTERBOXD_GRID_RE,
    LETTERBOXD_ITEM_SLUG_RE,
    LETTERBOXD_LIST_PAGE_RE,
    LETTERBOXD_TMDB_RE,
    fetch_page,
    fetch_page_or_none,
)

router = APIRouter(tags=["letterboxd"])

SERVICE_META = {"label": "Letterboxd", "health_check": None}


class LetterboxdAddRequest(BaseModel):
    url: str
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    dry_run: bool = False


@router.post("/api/arr/radarr/add-from-letterboxd")
# current_user_or_service, not current_user: stack-letterboxd-radarr.fish
# calls this unattended via __stack_api's service key (2026-08-06, carried
# over unchanged from services/radarr/router.py).
def radarr_add_from_letterboxd(payload: LetterboxdAddRequest, _=Depends(current_user_or_service)):
    cfg = ARR_APPS["radarr"]
    url = payload.url.strip()
    if "letterboxd.com/film/" not in url:
        fail("Not a Letterboxd film URL - expected something like https://letterboxd.com/film/<slug>/.", status_code=400)
    page_text = fetch_page(url)
    match = LETTERBOXD_TMDB_RE.search(page_text)
    if not match:
        fail("No TMDb link found on that Letterboxd page - it may be unmatched to TMDb.", status_code=404)
    tmdb_id = int(match.group(1))

    try:
        existing = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", params={"tmdbId": tmdb_id},
                              headers={"X-Api-Key": cfg["key"]}, timeout=20)
        existing.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't check whether Radarr already has this movie: {e}")
    existing_movies = existing.json()
    if existing_movies:
        m = existing_movies[0]
        return ok(f'"{m["title"]}" ({m.get("year")}) is already in Radarr.', tmdbId=tmdb_id, radarrId=m["id"], alreadyAdded=True)

    try:
        lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie/lookup/tmdb", params={"tmdbId": tmdb_id},
                            headers={"X-Api-Key": cfg["key"]}, timeout=20)
        lookup.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Radarr's TMDb lookup failed: {e}")
    movie = lookup.json()
    if not movie or not movie.get("title"):
        fail(f"Radarr has no TMDb match for id {tmdb_id}.", status_code=404)

    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)
    movie["qualityProfileId"] = quality_profile_id
    movie["rootFolderPath"] = root_folder_path
    movie["monitored"] = payload.monitored
    movie["addOptions"] = {"searchForMovie": payload.search}

    if payload.dry_run:
        return ok(f'Would add "{movie["title"]}" ({movie.get("year")}) to Radarr - dry run, nothing written.',
                   tmdbId=tmdb_id, dryRun=True)

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/movie", json=movie, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        fail(f"Radarr rejected the add: {e.response.text.strip() or e}")
    except httpx.HTTPError as e:
        fail(f"Radarr add failed: {e}")

    added = add.json()
    return ok(f'Added "{added.get("title", movie["title"])}" ({added.get("year", movie.get("year"))}) to Radarr.',
              tmdbId=tmdb_id, radarrId=added.get("id"))


class LetterboxdListAddRequest(BaseModel):
    url: str
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    limit: int | None = None
    dry_run: bool = False


@router.post("/api/arr/radarr/add-from-letterboxd-list")
# current_user_or_service, not current_user: stack-letterboxd-radarr-list.fish
# calls this unattended via __stack_api's service key (2026-08-06, carried
# over unchanged from services/radarr/router.py).
def radarr_add_from_letterboxd_list(payload: LetterboxdListAddRequest, _=Depends(current_user_or_service)):
    cfg = ARR_APPS["radarr"]
    base_url = payload.url.strip().rstrip("/")
    if LETTERBOXD_DISALLOWED_RE.search(base_url + "/"):
        fail(
            "That URL includes a sort/filter option Letterboxd's robots.txt disallows scraping "
            "(by/, genre/, decade/, year/, this/week/, size/large/, etc). Use the plain, unsorted URL.",
            status_code=400,
        )
    if not LETTERBOXD_GRID_RE.match(base_url):
        fail(
            "Not a recognized Letterboxd list/watchlist/filmography/collection URL - expected something like "
            "https://letterboxd.com/<user>/list/<slug>/, https://letterboxd.com/<user>/watchlist/, "
            "https://letterboxd.com/<user>/films/, https://letterboxd.com/actor/<slug>/, "
            "https://letterboxd.com/films/in/<collection>/, or https://letterboxd.com/films/popular/.",
            status_code=400,
        )

    first_page = fetch_page(base_url + "/")
    last_page = min(max((int(n) for n in LETTERBOXD_LIST_PAGE_RE.findall(first_page)), default=1), 10)

    slugs = list(dict.fromkeys(LETTERBOXD_ITEM_SLUG_RE.findall(first_page)))
    for page_num in range(2, last_page + 1):
        page_html = fetch_page_or_none(f"{base_url}/page/{page_num}/")
        if page_html is None:
            break
        slugs.extend(LETTERBOXD_ITEM_SLUG_RE.findall(page_html))
        time.sleep(0.2)
    slugs = list(dict.fromkeys(slugs))
    if not slugs:
        fail(
            "No films found on that Letterboxd page. Some pages (e.g. /films/popular/) render their "
            "poster grid client-side in JS and have no scrapeable server-rendered film data.",
            status_code=404,
        )

    limit = min(payload.limit, 720) if payload.limit else 720
    slugs = slugs[:limit]

    tmdb_ids = []
    unmatched = []
    total_slugs = len(slugs)
    for i, slug in enumerate(slugs, 1):
        match = LETTERBOXD_TMDB_RE.search(fetch_page(f"https://letterboxd.com/film/{slug}/"))
        if match:
            tmdb_ids.append(int(match.group(1)))
            print(f"letterboxd-list: [{i}/{total_slugs}] matched {slug} -> tmdb {match.group(1)}")
        else:
            unmatched.append(slug)
            print(f"letterboxd-list: [{i}/{total_slugs}] no TMDb match for {slug}")
        time.sleep(0.2)
    tmdb_ids = list(dict.fromkeys(tmdb_ids))

    try:
        library = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", headers={"X-Api-Key": cfg["key"]}, timeout=30)
        library.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Radarr's library: {e}")
    existing_tmdb_ids = {m["tmdbId"] for m in library.json()}

    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)

    added, already, failed = [], [], []
    total_movies = len(tmdb_ids)
    for i, tmdb_id in enumerate(tmdb_ids, 1):
        result = radarr_add_movie(cfg, tmdb_id, payload.monitored, payload.search, root_folder_path, quality_profile_id,
                                   existing_tmdb_ids, dry_run=payload.dry_run)
        if result["status"] == "already":
            already.append(tmdb_id)
        elif result["status"] == "added":
            added.append(result["title"])
        else:
            failed.append(result["reason"])

    verb = "would be added" if payload.dry_run else "added"
    summary = f"{len(added)} {verb}, {len(already)} already in Radarr, {len(failed)} failed"
    if unmatched:
        summary += f", {len(unmatched)} had no TMDb match"
    return ok(summary, added=added, alreadyCount=len(already), failed=failed, unmatched=unmatched, dryRun=payload.dry_run)
```

Create the empty package marker:

```bash
touch control-panel/services/letterboxd/__init__.py
```

- [ ] **Step 5: Remove the moved code from `services/radarr/router.py`**

Delete lines 1-233 of the current file (everything from the module docstring through the end of `radarr_add_from_letterboxd_list`, i.e. everything before `class ExcludeRequest`), replacing the top of the file with:

```python
"""Radarr-only routes with no Sonarr equivalent and no Letterboxd
involvement - the Letterboxd-driven routes that used to live here moved to
services/letterboxd/router.py (2026-08-06) once Letterboxd became a
first-class integration spanning both Radarr and Sonarr.
"""
import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.arr_client import ARR_APPS, get_movie_or_episode
from core.responses import fail, ok
from core.security import current_user

router = APIRouter(tags=["radarr"])

SERVICE_META = {"label": "Radarr", "health_check": None}


class ExcludeRequest(BaseModel):
    movieId: int


@router.post("/api/arr/radarr/exclude")
def arr_radarr_exclude(body: ExcludeRequest, _=Depends(current_user)):
    """The durable fix for movies that keep getting silently re-monitored by
    an import list's periodic sync - plain unmonitor only holds until the
    next sync. No Sonarr equivalent exists."""
    cfg = ARR_APPS["radarr"]
    movie = get_movie_or_episode("radarr", cfg, body.movieId)
    if movie is None:
        fail(f"Movie {body.movieId} not found in Radarr.", status_code=404)
    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/exclusions",
                        json={"tmdbId": movie.get("tmdbId"), "movieTitle": movie.get("title"), "movieYear": movie.get("year")},
                        headers={"X-Api-Key": cfg["key"]}, timeout=20)
        if r.status_code not in (200, 201, 400, 409):
            r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Exclusion failed: {e}")
    return ok(f"Excluded \"{movie.get('title')}\" from Radarr import lists.", movieId=body.movieId)
```

- [ ] **Step 6: Move `test_letterboxd_add_*` tests out of `test_radarr_sonarr_prowlarr_bazarr_router.py`**

Cut the two Letterboxd-add test functions (`test_letterboxd_add_short_circuits_when_already_in_radarr`, `test_letterboxd_add_rejects_non_letterboxd_url`, and any `test_letterboxd_add_requires_session_not_service_key`-style test) out of `tests/control_panel/test_radarr_sonarr_prowlarr_bazarr_router.py` and paste them into `tests/control_panel/test_letterboxd_router.py` (created in Step 1 above), keeping their `_login`/`_json_response` helper duplicated locally (matching this codebase's existing per-file helper-duplication convention rather than a new shared conftest addition, since `test_radarr_sonarr_prowlarr_bazarr_router.py` already duplicates `_login` itself rather than importing a shared one).

- [ ] **Step 7: Run both affected test files**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py tests/control_panel/test_radarr_sonarr_prowlarr_bazarr_router.py -q`
Expected: PASS, same total test count as before the move (nothing lost, nothing duplicated)

- [ ] **Step 8: Commit**

```bash
git add control-panel/services/letterboxd/ control-panel/services/radarr/router.py \
        tests/control_panel/test_letterboxd_router.py tests/control_panel/test_radarr_sonarr_prowlarr_bazarr_router.py
git commit -m "refactor: extract Letterboxd routes into services/letterboxd/"
```

---

### Task 3: Slug→TMDb dedup cache (feature #9)

Wires `LetterboxdTmdbCache` (Task 1) into `radarr_add_from_letterboxd_list`'s slug-resolution loop so a re-scraped list skips the per-slug Letterboxd page fetch for any slug already resolved by a prior run.

**Files:**
- Create: `control-panel/services/letterboxd/cache.py`
- Modify: `control-panel/services/letterboxd/router.py` (the `for i, slug in enumerate(slugs, 1):` loop in `radarr_add_from_letterboxd_list`)
- Test: `tests/control_panel/test_letterboxd_cache.py`

**Interfaces:**
- Consumes: `models.letterboxd_cache.LetterboxdTmdbCache`, `core.db.SessionLocal`.
- Produces: `services.letterboxd.cache.resolve_tmdb_ids(db, slugs: list[str]) -> tuple[list[int], list[str]]` — returns `(tmdb_ids, unmatched_slugs)`, using cached rows where present and fetching+caching the rest. Later tasks (6) extend this signature's caching to also record `media_type`.

- [ ] **Step 1: Write the failing test**

```python
# tests/control_panel/test_letterboxd_cache.py
from unittest.mock import MagicMock

import httpx


def test_resolve_tmdb_ids_skips_cached_slugs(cp_main_app, monkeypatch):
    from models.letterboxd_cache import LetterboxdTmdbCache
    from services.letterboxd.cache import resolve_tmdb_ids

    db = cp_main_app.SessionLocal()
    db.add(LetterboxdTmdbCache(slug="the-matrix", tmdb_id=603, media_type="movie"))
    db.commit()

    fetch_calls = []

    def fake_get(url, headers=None, timeout=None, follow_redirects=None, **kwargs):
        fetch_calls.append(url)
        return MagicMock(text='themoviedb.org/movie/27205', raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)

    tmdb_ids, unmatched = resolve_tmdb_ids(db, ["the-matrix", "inception"])

    assert tmdb_ids == [603, 27205]
    assert unmatched == []
    # only "inception" should have triggered a real fetch - "the-matrix" was cached
    assert len(fetch_calls) == 1
    assert "inception" in fetch_calls[0]

    cached = db.query(LetterboxdTmdbCache).filter_by(slug="inception").one()
    assert cached.tmdb_id == 27205
    db.close()


def test_resolve_tmdb_ids_caches_unmatched_slugs_too(cp_main_app, monkeypatch):
    from models.letterboxd_cache import LetterboxdTmdbCache
    from services.letterboxd.cache import resolve_tmdb_ids

    db = cp_main_app.SessionLocal()

    def fake_get(url, headers=None, timeout=None, follow_redirects=None, **kwargs):
        return MagicMock(text='<html>no tmdb link here</html>', raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)

    tmdb_ids, unmatched = resolve_tmdb_ids(db, ["some-unmatched-short"])

    assert tmdb_ids == []
    assert unmatched == ["some-unmatched-short"]
    cached = db.query(LetterboxdTmdbCache).filter_by(slug="some-unmatched-short").one()
    assert cached.tmdb_id is None
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_cache.py -x -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.letterboxd.cache'`

- [ ] **Step 3: Write `cache.py`**

```python
# control-panel/services/letterboxd/cache.py
"""Slug -> TMDb id dedup cache (models.letterboxd_cache.LetterboxdTmdbCache)
- a re-scraped list/watchlist skips the per-slug Letterboxd film-page fetch
for any slug a prior run already resolved. A slug with no TMDb match gets
cached too (tmdb_id=None), so re-runs don't keep re-fetching known dead
ends - Task 6 (TV crossover) is what actually makes use of a cached
media_type="tv" row instead of re-treating it as a permanent dead end.
"""
from sqlalchemy.orm import Session

from models.letterboxd_cache import LetterboxdTmdbCache
from services.letterboxd.scraping import LETTERBOXD_TMDB_RE, fetch_page


def resolve_tmdb_ids(db: Session, slugs: list[str]) -> tuple[list[int], list[str]]:
    """Returns (tmdb_ids, unmatched_slugs), same shape the caller
    previously built inline in the fetch loop. Order of tmdb_ids follows
    `slugs`' order, not cache-hit-then-miss order."""
    cached_rows = {
        row.slug: row
        for row in db.query(LetterboxdTmdbCache).filter(LetterboxdTmdbCache.slug.in_(slugs)).all()
    }

    tmdb_ids: list[int] = []
    unmatched: list[str] = []
    for slug in slugs:
        row = cached_rows.get(slug)
        if row is None:
            match = LETTERBOXD_TMDB_RE.search(fetch_page(f"https://letterboxd.com/film/{slug}/"))
            tmdb_id = int(match.group(1)) if match else None
            row = LetterboxdTmdbCache(slug=slug, tmdb_id=tmdb_id, media_type="movie")
            db.add(row)
            db.commit()
        if row.tmdb_id is not None:
            tmdb_ids.append(row.tmdb_id)
        else:
            unmatched.append(slug)
    return tmdb_ids, unmatched
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_cache.py -x -q`
Expected: PASS

- [ ] **Step 5: Wire `resolve_tmdb_ids` into the list-add route**

In `control-panel/services/letterboxd/router.py`, replace the fetch loop in `radarr_add_from_letterboxd_list`:

```python
    tmdb_ids = []
    unmatched = []
    total_slugs = len(slugs)
    for i, slug in enumerate(slugs, 1):
        match = LETTERBOXD_TMDB_RE.search(fetch_page(f"https://letterboxd.com/film/{slug}/"))
        if match:
            tmdb_ids.append(int(match.group(1)))
            print(f"letterboxd-list: [{i}/{total_slugs}] matched {slug} -> tmdb {match.group(1)}")
        else:
            unmatched.append(slug)
            print(f"letterboxd-list: [{i}/{total_slugs}] no TMDb match for {slug}")
        time.sleep(0.2)
    tmdb_ids = list(dict.fromkeys(tmdb_ids))
```

with:

```python
    from core.db import SessionLocal
    from services.letterboxd.cache import resolve_tmdb_ids

    db = SessionLocal()
    try:
        tmdb_ids, unmatched = resolve_tmdb_ids(db, slugs)
    finally:
        db.close()
    tmdb_ids = list(dict.fromkeys(tmdb_ids))
    print(f"letterboxd-list: resolved {len(tmdb_ids)} tmdb id(s), {len(unmatched)} unmatched, out of {len(slugs)} slug(s)")
```

Remove the now-unused `time` import's `sleep(0.2)` call from this specific loop only — the pagination loop's `time.sleep(0.2)` (fetching list pages 2-10) is untouched and stays, since that's still a live per-page fetch, not a cached lookup. The `import time` statement stays at the top of the file (still used by the pagination loop).

- [ ] **Step 6: Re-run the full Letterboxd router test file to confirm the wiring didn't break the existing list-add behavior**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py tests/control_panel/test_letterboxd_cache.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add control-panel/services/letterboxd/cache.py control-panel/services/letterboxd/router.py \
        tests/control_panel/test_letterboxd_cache.py
git commit -m "feat: cache Letterboxd slug->TMDb id lookups to skip re-fetching known slugs"
```

---

### Task 4: Rating-aware quality-profile mapping (feature #1)

Adds an optional `rating_quality_map` field to `LetterboxdListAddRequest`. When present, each film's Radarr quality profile is chosen by the *page owner's own Letterboxd rating* for that film (only meaningful on `/<user>/films/` or `/<user>/watchlist/`-shaped URLs where the requester is scraping their own ratings) instead of the single `quality_profile` for the whole batch.

**Files:**
- Modify: `control-panel/services/letterboxd/router.py`
- Modify: `control-panel/core/arr_client.py` (new small helper, see Step 3)
- Test: `tests/control_panel/test_letterboxd_router.py` (append)

**Interfaces:**
- Consumes: `services.letterboxd.scraping.scrape_slugs_with_ratings(page_html: str) -> list[tuple[str, int | None]]` (Task 2).
- Produces: `LetterboxdListAddRequest.rating_quality_map: dict[str, str] | None` (keys are string ratings `"1"`-`"10"`, values are Radarr quality-profile names — string-keyed because Pydantic/JSON object keys are always strings), `core.arr_client.radarr_quality_profile_id_by_name(cfg, name: str) -> int | None`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/control_panel/test_letterboxd_router.py
def test_letterboxd_list_add_applies_rating_quality_map(cp_main_app, monkeypatch):
    list_html = '''
    <html>
      <a href="/page/1/"></a>
      <li><div data-item-slug="high-rated-film"></div>
        <p class="poster-viewingdata"><span class="rating -micro -darker rated-10">★★★★★</span></p></li>
      <li><div data-item-slug="low-rated-film"></div>
        <p class="poster-viewingdata"><span class="rating -micro -darker rated-2">★</span></p></li>
    </html>
    '''
    film_pages = {
        "high-rated-film": "themoviedb.org/movie/111",
        "low-rated-film": "themoviedb.org/movie/222",
    }
    quality_profiles = [{"id": 5, "name": "Remux-1080p"}, {"id": 9, "name": "HD-1080p"}]
    posted_movies = []

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if url.rstrip("/").endswith("/bear/films") or "/bear/films/" in url:
            return MagicMock(text=list_html, raise_for_status=MagicMock())
        for slug, tmdb_html in film_pages.items():
            if slug in url:
                return MagicMock(text=tmdb_html, raise_for_status=MagicMock())
        if url.endswith("/rootfolder"):
            return MagicMock(json=lambda: [{"path": "/data/movies"}], raise_for_status=MagicMock())
        if url.endswith("/qualityprofile"):
            return MagicMock(json=lambda: quality_profiles, raise_for_status=MagicMock())
        if url.endswith("/movie/lookup/tmdb"):
            tmdb_id = params["tmdbId"]
            return MagicMock(json=lambda: {"title": f"Film {tmdb_id}", "year": 2020}, raise_for_status=MagicMock())
        if url.endswith("/movie"):
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        return MagicMock(json=lambda: {}, raise_for_status=MagicMock())

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        posted_movies.append(json)
        return MagicMock(json=lambda: {**json, "title": json.get("title")}, raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd-list", json={
        "url": "https://letterboxd.com/bear/films/",
        "rating_quality_map": {"10": "Remux-1080p", "2": "HD-1080p"},
    })
    assert resp.status_code == 200
    by_tmdb = {m["tmdbId"]: m for m in posted_movies}
    assert by_tmdb[111]["qualityProfileId"] == 5
    assert by_tmdb[222]["qualityProfileId"] == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py::test_letterboxd_list_add_applies_rating_quality_map -x -q`
Expected: FAIL (`rating_quality_map` field doesn't exist yet / every movie gets the same default quality profile)

- [ ] **Step 3: Add `radarr_quality_profile_id_by_name` to `core/arr_client.py`**

Append after `radarr_root_folder_and_profile` (around line 396):

```python
def radarr_quality_profile_id_by_name(cfg: dict, name: str) -> int | None:
    try:
        profiles = httpx.get(f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
    except httpx.HTTPError:
        return None
    return next((p["id"] for p in profiles if p["name"] == name), None)
```

- [ ] **Step 4: Wire rating-based per-film quality selection into the route**

In `control-panel/services/letterboxd/router.py`:

1. Add the field to `LetterboxdListAddRequest`:

```python
class LetterboxdListAddRequest(BaseModel):
    url: str
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    limit: int | None = None
    dry_run: bool = False
    rating_quality_map: dict[str, str] | None = None
```

2. Replace the slug-scraping section (`slugs = list(dict.fromkeys(LETTERBOXD_ITEM_SLUG_RE.findall(first_page)))` through the pagination loop) so it also captures ratings when `rating_quality_map` is set:

```python
    if payload.rating_quality_map:
        from services.letterboxd.scraping import scrape_slugs_with_ratings
        slug_ratings: dict[str, int | None] = dict(scrape_slugs_with_ratings(first_page))
        for page_num in range(2, last_page + 1):
            page_html = fetch_page_or_none(f"{base_url}/page/{page_num}/")
            if page_html is None:
                break
            slug_ratings.update(dict(scrape_slugs_with_ratings(page_html)))
            time.sleep(0.2)
        slugs = list(slug_ratings.keys())
    else:
        slug_ratings = {}
        slugs = list(dict.fromkeys(LETTERBOXD_ITEM_SLUG_RE.findall(first_page)))
        for page_num in range(2, last_page + 1):
            page_html = fetch_page_or_none(f"{base_url}/page/{page_num}/")
            if page_html is None:
                break
            slugs.extend(LETTERBOXD_ITEM_SLUG_RE.findall(page_html))
            time.sleep(0.2)
        slugs = list(dict.fromkeys(slugs))
```

3. After `root_folder_path, quality_profile_id = radarr_root_folder_and_profile(...)`, build a slug→profile-id map and pass per-film profile ids into the add loop:

```python
    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)

    rating_profile_ids: dict[str, int] = {}
    if payload.rating_quality_map:
        for rating_str, profile_name in payload.rating_quality_map.items():
            pid = radarr_quality_profile_id_by_name(cfg, profile_name)
            if pid is not None:
                rating_profile_ids[rating_str] = pid

    # slug -> resolved tmdb_id, needed to look back up a film's rating when
    # choosing its quality profile - resolve_tmdb_ids only returns the ids,
    # not which slug produced which id, so track that mapping here too.
    slug_to_tmdb: dict[str, int] = {}
    if payload.rating_quality_map:
        db = SessionLocal()
        try:
            for slug in slugs:
                cached = db.query(LetterboxdTmdbCache).filter_by(slug=slug).first()
                if cached and cached.tmdb_id is not None:
                    slug_to_tmdb[slug] = cached.tmdb_id
        finally:
            db.close()

    added, already, failed = [], [], []
    total_movies = len(tmdb_ids)
    for i, tmdb_id in enumerate(tmdb_ids, 1):
        film_quality_profile_id = quality_profile_id
        if payload.rating_quality_map:
            slug = next((s for s, t in slug_to_tmdb.items() if t == tmdb_id), None)
            rating = slug_ratings.get(slug) if slug else None
            if rating is not None and str(rating) in rating_profile_ids:
                film_quality_profile_id = rating_profile_ids[str(rating)]
        result = radarr_add_movie(cfg, tmdb_id, payload.monitored, payload.search, root_folder_path, film_quality_profile_id,
                                   existing_tmdb_ids, dry_run=payload.dry_run)
        if result["status"] == "already":
            already.append(tmdb_id)
        elif result["status"] == "added":
            added.append(result["title"])
        else:
            failed.append(result["reason"])
```

4. Add the two new imports at the top of the file:

```python
from core.arr_client import ARR_APPS, radarr_add_movie, radarr_quality_profile_id_by_name, radarr_root_folder_and_profile
from core.db import SessionLocal
from models.letterboxd_cache import LetterboxdTmdbCache
```

- [ ] **Step 5: Run test to verify it passes**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py -q`
Expected: PASS (including the pre-existing tests — rating mapping only activates when `rating_quality_map` is provided, so the default path is unchanged)

- [ ] **Step 6: Commit**

```bash
git add control-panel/services/letterboxd/router.py control-panel/core/arr_client.py \
        tests/control_panel/test_letterboxd_router.py
git commit -m "feat: rating-aware quality-profile mapping for Letterboxd list adds"
```

---

### Task 5: Tag scraping into Radarr tags (feature #4)

Adds an optional `tags_as_radarr_tags: bool` field. When true, each film's Letterboxd tags (scraped from the *page owner's* logged/reviewed film page, `https://letterboxd.com/<user>/film/<slug>/`) are created (if needed) and attached as Radarr tags on add.

**Files:**
- Modify: `control-panel/services/letterboxd/router.py`
- Modify: `control-panel/core/arr_client.py`
- Modify: `control-panel/services/letterboxd/scraping.py` (verify/adjust `LETTERBOXD_TAG_RE` per Step 1)
- Test: `tests/control_panel/test_letterboxd_router.py` (append)

**Interfaces:**
- Consumes: `services.letterboxd.scraping.scrape_tags`, `services.letterboxd.scraping.LETTERBOXD_TAG_RE`.
- Produces: `LetterboxdListAddRequest.tags_as_radarr_tags: bool = False`, `core.arr_client.radarr_ensure_tags(cfg: dict, tag_names: list[str]) -> list[int]`.

- [ ] **Step 1: Verify the tag markup live before writing the regex-dependent code**

`LETTERBOXD_TAG_RE` in `scraping.py` (Task 2) was written from documented community-scraper conventions, not confirmed live in this session (the specific film/user pages fetched had no tags set). Before proceeding, fetch a real tagged entry and confirm:

```bash
curl -sS -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36" \
  "https://letterboxd.com/<a-username-you-know-tags-films>/film/<a-tagged-film-slug>/" -o /tmp/lb_tagged.html
grep -o 'href="/[^"]*tag/[^"]*"[^>]*>[^<]*' /tmp/lb_tagged.html
```

If the actual markup differs from `href="/[^/]+/tag/([^/"]+)/"[^>]*class="tag"`, update `LETTERBOXD_TAG_RE` in `scraping.py` to match what's actually returned before continuing — do not guess further, re-derive the pattern from the real HTML captured here.

- [ ] **Step 2: Write the failing test**

```python
# append to tests/control_panel/test_letterboxd_router.py
def test_letterboxd_list_add_attaches_scraped_tags(cp_main_app, monkeypatch):
    list_html = '<html><a href="/page/1/"></a><li><div data-item-slug="tagged-film"></div></li></html>'
    user_film_html = '<html><a href="/bear/tag/rewatch/" class="tag">rewatch</a><a href="/bear/tag/a24/" class="tag">a24</a></html>'
    tags_in_radarr = [{"id": 1, "label": "rewatch"}]
    posted_movies = []
    created_tags = []

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com/bear/list/tagged-list" in url and "/film/" not in url:
            return MagicMock(text=list_html, raise_for_status=MagicMock())
        if "letterboxd.com/bear/film/tagged-film" in url:
            return MagicMock(text=user_film_html, raise_for_status=MagicMock())
        if "letterboxd.com/film/tagged-film" in url:
            return MagicMock(text="themoviedb.org/movie/500", raise_for_status=MagicMock())
        if url.endswith("/rootfolder"):
            return MagicMock(json=lambda: [{"path": "/data/movies"}], raise_for_status=MagicMock())
        if url.endswith("/qualityprofile"):
            return MagicMock(json=lambda: [{"id": 1, "name": "Unlimited"}], raise_for_status=MagicMock())
        if url.endswith("/tag"):
            return MagicMock(json=lambda: tags_in_radarr, raise_for_status=MagicMock())
        if url.endswith("/movie/lookup/tmdb"):
            return MagicMock(json=lambda: {"title": "Tagged Film", "year": 2021}, raise_for_status=MagicMock())
        if url.endswith("/movie"):
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        return MagicMock(json=lambda: {}, raise_for_status=MagicMock())

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        if url.endswith("/tag"):
            created_tags.append(json["label"])
            return MagicMock(json=lambda: {"id": 2, "label": json["label"]}, raise_for_status=MagicMock())
        posted_movies.append(json)
        return MagicMock(json=lambda: {**json, "title": json.get("title")}, raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd-list", json={
        "url": "https://letterboxd.com/bear/list/tagged-list/",
        "tags_as_radarr_tags": True,
    })
    assert resp.status_code == 200
    assert created_tags == ["a24"]  # "rewatch" already existed (id 1), only "a24" needed creating
    assert posted_movies[0]["tags"] == [1, 2]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py::test_letterboxd_list_add_attaches_scraped_tags -x -q`
Expected: FAIL (`tags_as_radarr_tags` field doesn't exist / no tags attached)

- [ ] **Step 4: Add `radarr_ensure_tags` to `core/arr_client.py`**

Append after `radarr_quality_profile_id_by_name` (Task 4, Step 3):

```python
def radarr_ensure_tags(cfg: dict, tag_names: list[str]) -> list[int]:
    """Returns the Radarr tag ids for tag_names, creating any that don't
    exist yet. Radarr's v3 tag API requires creating a tag via POST /tag
    before it can be referenced by id on a movie - there's no
    create-on-attach shortcut."""
    if not tag_names:
        return []
    try:
        existing = httpx.get(f"{cfg['url']}/api/{cfg['api']}/tag", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Radarr's tags: {e}")
    by_label = {t["label"]: t["id"] for t in existing}

    ids = []
    for name in tag_names:
        if name in by_label:
            ids.append(by_label[name])
            continue
        try:
            created = httpx.post(f"{cfg['url']}/api/{cfg['api']}/tag", json={"label": name},
                                  headers={"X-Api-Key": cfg["key"]}, timeout=15)
            created.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"Couldn't create Radarr tag '{name}': {e}")
        new_id = created.json()["id"]
        by_label[name] = new_id
        ids.append(new_id)
    return ids
```

- [ ] **Step 5: Wire tag scraping + attachment into the route**

In `control-panel/services/letterboxd/router.py`:

1. Add the field to `LetterboxdListAddRequest`: `tags_as_radarr_tags: bool = False`
2. Import `radarr_ensure_tags` and `scrape_tags` at the top.
3. After resolving `tmdb_ids`/`unmatched` (post-Task-3's `resolve_tmdb_ids` call), when `payload.tags_as_radarr_tags` is set, scrape each matched slug's owner-film page for tags and build a `tmdb_id -> tag_ids` map:

```python
    slug_to_tag_ids: dict[int, list[int]] = {}
    if payload.tags_as_radarr_tags:
        # base_url is like https://letterboxd.com/<user>/list/<slug> or
        # https://letterboxd.com/<user>/watchlist - the owner segment is
        # always the first path component, valid for every URL shape
        # LETTERBOXD_GRID_RE allows except the bare films/popular/collection
        # ones (which have no single owner - tags_as_radarr_tags on those
        # scrapes zero tags, not an error, since a film with no scraped
        # tags is a normal outcome for this feature).
        owner = base_url.replace("https://letterboxd.com/", "").split("/")[0]
        db = SessionLocal()
        try:
            for slug in slugs:
                cached = db.query(LetterboxdTmdbCache).filter_by(slug=slug).first()
                if not cached or cached.tmdb_id is None:
                    continue
                user_film_html = fetch_page_or_none(f"https://letterboxd.com/{owner}/film/{slug}/")
                if not user_film_html:
                    continue
                tag_names = scrape_tags(user_film_html)
                if tag_names:
                    slug_to_tag_ids[cached.tmdb_id] = radarr_ensure_tags(cfg, tag_names)
                time.sleep(0.2)
        finally:
            db.close()
```

4. Extend `radarr_add_movie` calls to pass tags through. `core.arr_client.radarr_add_movie` doesn't currently accept a `tags` parameter — add one:

In `core/arr_client.py`, change the signature:

```python
def radarr_add_movie(cfg, tmdb_id: int, monitored: bool, search: bool, root_folder_path: str, quality_profile_id: int,
                      existing_tmdb_ids: set[int], dry_run: bool = False, tag_ids: list[int] | None = None) -> dict:
    if tmdb_id in existing_tmdb_ids:
        return {"status": "already", "title": None, "tmdbId": tmdb_id}
    try:
        lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie/lookup/tmdb", params={"tmdbId": tmdb_id},
                            headers={"X-Api-Key": cfg["key"]}, timeout=20)
        lookup.raise_for_status()
        movie = lookup.json()
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f"tmdb {tmdb_id}: lookup failed ({e})"}
    if not movie or not movie.get("title"):
        return {"status": "failed", "reason": f"tmdb {tmdb_id}: no Radarr match"}

    movie["qualityProfileId"] = quality_profile_id
    movie["rootFolderPath"] = root_folder_path
    movie["monitored"] = monitored
    movie["addOptions"] = {"searchForMovie": search}
    if tag_ids:
        movie["tags"] = tag_ids
```

(rest of the function body unchanged). This is a backward-compatible signature change (new keyword arg with a default) — every existing caller (Task 2's list-add route, without tags) keeps working unmodified.

5. Back in the router's add loop, pass `tag_ids=slug_to_tag_ids.get(tmdb_id)`:

```python
        result = radarr_add_movie(cfg, tmdb_id, payload.monitored, payload.search, root_folder_path, film_quality_profile_id,
                                   existing_tmdb_ids, dry_run=payload.dry_run, tag_ids=slug_to_tag_ids.get(tmdb_id))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add control-panel/services/letterboxd/router.py control-panel/services/letterboxd/scraping.py \
        control-panel/core/arr_client.py tests/control_panel/test_letterboxd_router.py
git commit -m "feat: attach scraped Letterboxd tags as Radarr tags on add"
```

---

### Task 6: TV/Sonarr crossover for unmatched titles (feature #3)

When a Letterboxd film-page slug has no TMDb *movie* match (`unmatched`), attempts a Sonarr series match by title/year (scraped from the same page's `og:title` meta tag) via Sonarr's own `/api/v3/series/lookup?term=` — no TMDB API call needed.

**Files:**
- Modify: `control-panel/services/letterboxd/router.py`
- Modify: `control-panel/services/letterboxd/cache.py`
- Test: `tests/control_panel/test_letterboxd_router.py` (append)

**Interfaces:**
- Consumes: `core.arr_client.sonarr_add_series`, `core.arr_client.sonarr_root_folder_and_profile`, `services.letterboxd.scraping.scrape_title_year` (both already exist — `sonarr_add_series`/`sonarr_root_folder_and_profile` were already present in `core/arr_client.py` before this plan, ready to use unmodified).
- Produces: `services.letterboxd.cache.resolve_tv_crossovers(db, unmatched_slugs: list[str]) -> tuple[list[dict], list[str]]` — returns `(matches, still_unmatched)` where each match is `{"slug": str, "title": str, "year": int, "tvdb_id": int}`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/control_panel/test_letterboxd_router.py
def test_letterboxd_list_add_crosses_over_unmatched_title_to_sonarr(cp_main_app, monkeypatch):
    list_html = '<html><a href="/page/1/"></a><li><div data-item-slug="a-tv-miniseries"></div></li></html>'
    film_page_html = '<html><meta property="og:title" content="A TV Miniseries (2022)"/>no tmdb movie link here</html>'
    sonarr_series_added = []

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com/bear/list/tv-list" in url and "/film/" not in url:
            return MagicMock(text=list_html, raise_for_status=MagicMock())
        if "letterboxd.com/film/a-tv-miniseries" in url:
            return MagicMock(text=film_page_html, raise_for_status=MagicMock())
        if url.endswith("/movie") and "radarr" in url:
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        if url.endswith("/rootfolder") and "radarr" in url:
            return MagicMock(json=lambda: [{"path": "/data/movies"}], raise_for_status=MagicMock())
        if url.endswith("/qualityprofile") and "radarr" in url:
            return MagicMock(json=lambda: [{"id": 1, "name": "Unlimited"}], raise_for_status=MagicMock())
        if url.endswith("/rootfolder") and "sonarr" in url:
            return MagicMock(json=lambda: [{"path": "/data/shows"}], raise_for_status=MagicMock())
        if url.endswith("/qualityprofile") and "sonarr" in url:
            return MagicMock(json=lambda: [{"id": 2, "name": "Any"}], raise_for_status=MagicMock())
        if url.endswith("/series") and "sonarr" in url:
            return MagicMock(json=lambda: [], raise_for_status=MagicMock())
        if url.endswith("/series/lookup"):
            assert params["term"] == "A TV Miniseries"
            return MagicMock(json=lambda: [{"title": "A TV Miniseries", "tvdbId": 777, "year": 2022}], raise_for_status=MagicMock())
        return MagicMock(json=lambda: {}, raise_for_status=MagicMock())

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        if url.endswith("/series"):
            sonarr_series_added.append(json)
            return MagicMock(json=lambda: {**json, "title": json.get("title")}, raise_for_status=MagicMock())
        return MagicMock(json=lambda: {}, raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd-list", json={
        "url": "https://letterboxd.com/bear/list/tv-list/",
        "sonarr_crossover": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["tvCrossoverCount"] == 1
    assert sonarr_series_added[0]["tvdbId"] == 777
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py::test_letterboxd_list_add_crosses_over_unmatched_title_to_sonarr -x -q`
Expected: FAIL (`sonarr_crossover` field doesn't exist / `tvCrossoverCount` missing)

- [ ] **Step 3: Add `resolve_tv_crossovers` to `cache.py`**

```python
# append to control-panel/services/letterboxd/cache.py
from core.arr_client import ARR_APPS
from services.letterboxd.scraping import scrape_title_year


def resolve_tv_crossovers(db: Session, unmatched_slugs: list[str]) -> tuple[list[dict], list[str]]:
    """For each slug with no TMDb movie match, checks Sonarr's own
    series-lookup-by-title to catch titles Letterboxd carries as a film
    entry that are actually a miniseries/TV special - no TMDB API call
    needed, Sonarr's /series/lookup?term= does its own title search.
    Returns (matches, still_unmatched); matches is
    [{"slug", "title", "year", "tvdb_id"}, ...]."""
    import httpx

    cfg = ARR_APPS["sonarr"]
    matches: list[dict] = []
    still_unmatched: list[str] = []
    for slug in unmatched_slugs:
        row = db.query.__self__ if False else None  # placeholder removed below
        film_html = None
        try:
            r = httpx.get(f"https://letterboxd.com/film/{slug}/", headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            }, timeout=15, follow_redirects=True)
            r.raise_for_status()
            film_html = r.text
        except httpx.HTTPError:
            still_unmatched.append(slug)
            continue
        title_year = scrape_title_year(film_html)
        if title_year is None:
            still_unmatched.append(slug)
            continue
        title, year = title_year
        try:
            lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/series/lookup", params={"term": title},
                                headers={"X-Api-Key": cfg["key"]}, timeout=20)
            lookup.raise_for_status()
            results = lookup.json()
        except httpx.HTTPError:
            still_unmatched.append(slug)
            continue
        # Require an exact title AND year match - series/lookup is a fuzzy
        # title search and can return unrelated shows for a generic title.
        exact = next((s for s in results if s.get("title") == title and s.get("year") == year), None)
        if exact is None or not exact.get("tvdbId"):
            still_unmatched.append(slug)
            continue
        matches.append({"slug": slug, "title": title, "year": year, "tvdb_id": exact["tvdbId"]})
    return matches, still_unmatched
```

Remove the stray placeholder line (`row = db.query...`) — it was left in by mistake; the function does not need a `db` lookup, `db` stays as a parameter only for signature symmetry with `resolve_tmdb_ids` and because Task 8's tracked-list sync calls both with the same session. Corrected function has no `db.query` call inside the loop at all.

- [ ] **Step 4: Wire crossover into the route**

In `control-panel/services/letterboxd/router.py`:

1. Add fields to `LetterboxdListAddRequest`: `sonarr_crossover: bool = False`
2. Import `resolve_tv_crossovers`, `sonarr_add_series`, `sonarr_root_folder_and_profile` at the top.
3. After the existing `tmdb_ids, unmatched = resolve_tmdb_ids(db, slugs)` call (Task 3), add:

```python
    tv_added, tv_already, tv_failed = [], [], []
    if payload.sonarr_crossover and unmatched:
        sonarr_cfg = ARR_APPS["sonarr"]
        db = SessionLocal()
        try:
            tv_matches, unmatched = resolve_tv_crossovers(db, unmatched)
        finally:
            db.close()
        if tv_matches:
            try:
                sonarr_library = httpx.get(f"{sonarr_cfg['url']}/api/{sonarr_cfg['api']}/series",
                                            headers={"X-Api-Key": sonarr_cfg["key"]}, timeout=30)
                sonarr_library.raise_for_status()
            except httpx.HTTPError as e:
                fail(f"Couldn't read Sonarr's library: {e}")
            existing_tvdb_ids = {s["tvdbId"] for s in sonarr_library.json()}
            sonarr_root_folder_path, sonarr_quality_profile_id = sonarr_root_folder_and_profile(sonarr_cfg, None, None)
            for tv_match in tv_matches:
                result = sonarr_add_series(sonarr_cfg, tv_match["tvdb_id"], payload.monitored, payload.search,
                                            sonarr_root_folder_path, sonarr_quality_profile_id, existing_tvdb_ids,
                                            dry_run=payload.dry_run)
                if result["status"] == "already":
                    tv_already.append(tv_match["title"])
                elif result["status"] == "added":
                    tv_added.append(result["title"])
                else:
                    tv_failed.append(result["reason"])
```

4. Include the crossover counts in the response:

```python
    verb = "would be added" if payload.dry_run else "added"
    summary = f"{len(added)} {verb}, {len(already)} already in Radarr, {len(failed)} failed"
    if unmatched:
        summary += f", {len(unmatched)} had no TMDb match"
    if tv_added or tv_already or tv_failed:
        summary += f"; {len(tv_added)} TV crossover {verb} to Sonarr, {len(tv_already)} already in Sonarr, {len(tv_failed)} failed"
    return ok(summary, added=added, alreadyCount=len(already), failed=failed, unmatched=unmatched, dryRun=payload.dry_run,
              tvCrossoverAdded=tv_added, tvCrossoverAlready=tv_already, tvCrossoverFailed=tv_failed,
              tvCrossoverCount=len(tv_added) + len(tv_already))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add control-panel/services/letterboxd/router.py control-panel/services/letterboxd/cache.py \
        tests/control_panel/test_letterboxd_router.py
git commit -m "feat: cross over TMDb-unmatched Letterboxd titles to Sonarr via series lookup"
```

---

### Task 7: Sync telemetry (feature #10)

Writes a `LetterboxdSyncLog` row at the end of every `add-from-letterboxd-list` run, and adds `GET /api/arr/letterboxd/history` to read them back.

**Files:**
- Create: `control-panel/services/letterboxd/sync.py`
- Modify: `control-panel/services/letterboxd/router.py`
- Test: `tests/control_panel/test_letterboxd_sync.py`

**Interfaces:**
- Consumes: `models.letterboxd_sync_log.LetterboxdSyncLog`, `core.db.SessionLocal`.
- Produces: `services.letterboxd.sync.record_sync_log(db, list_url, *, matched, unmatched, added, already, failed, tv_crossover=0, error_detail=None) -> None`, route `GET /api/arr/letterboxd/history` returning `{"ok": true, "message": ..., "runs": [{"listUrl", "runAt", "matched", "unmatched", "added", "already", "failed", "tvCrossover"}]}` (most recent first, capped at 100 rows).

- [ ] **Step 1: Write the failing test**

```python
# tests/control_panel/test_letterboxd_sync.py
from fastapi.testclient import TestClient


def _login(client, main_module, password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200


def test_record_sync_log_writes_a_row(cp_main_app):
    from models.letterboxd_sync_log import LetterboxdSyncLog
    from services.letterboxd.sync import record_sync_log

    db = cp_main_app.SessionLocal()
    record_sync_log(db, "https://letterboxd.com/bear/watchlist/", matched=8, unmatched=1, added=3, already=5,
                     failed=0, tv_crossover=1)
    row = db.query(LetterboxdSyncLog).filter_by(list_url="https://letterboxd.com/bear/watchlist/").one()
    assert row.added == 3
    assert row.tv_crossover == 1
    db.close()


def test_history_endpoint_returns_runs_most_recent_first(cp_main_app):
    from services.letterboxd.sync import record_sync_log

    db = cp_main_app.SessionLocal()
    record_sync_log(db, "https://letterboxd.com/bear/list/a/", matched=1, unmatched=0, added=1, already=0, failed=0)
    record_sync_log(db, "https://letterboxd.com/bear/list/b/", matched=2, unmatched=0, added=2, already=0, failed=0)
    db.close()

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.get("/api/arr/letterboxd/history")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 2
    assert runs[0]["listUrl"] == "https://letterboxd.com/bear/list/b/"  # most recent first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_sync.py -x -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.letterboxd.sync'`

- [ ] **Step 3: Write `sync.py`**

```python
# control-panel/services/letterboxd/sync.py
"""Sync telemetry: one LetterboxdSyncLog row per add-from-letterboxd-list
run (manual or scheduled), plus the GET /api/arr/letterboxd/history read
route - see models/letterboxd_sync_log.py."""
from sqlalchemy.orm import Session

from models.letterboxd_sync_log import LetterboxdSyncLog

HISTORY_PAGE_SIZE = 100


def record_sync_log(db: Session, list_url: str, *, matched: int, unmatched: int, added: int, already: int,
                     failed: int, tv_crossover: int = 0, error_detail: str | None = None) -> None:
    db.add(LetterboxdSyncLog(list_url=list_url, matched=matched, unmatched=unmatched, added=added, already=already,
                              failed=failed, tv_crossover=tv_crossover, error_detail=error_detail))
    db.commit()


def recent_sync_logs(db: Session) -> list[dict]:
    rows = (
        db.query(LetterboxdSyncLog)
        .order_by(LetterboxdSyncLog.run_at.desc())
        .limit(HISTORY_PAGE_SIZE)
        .all()
    )
    return [
        {
            "listUrl": r.list_url,
            "runAt": r.run_at.isoformat() if r.run_at else None,
            "matched": r.matched,
            "unmatched": r.unmatched,
            "added": r.added,
            "already": r.already,
            "failed": r.failed,
            "tvCrossover": r.tv_crossover,
            "errorDetail": r.error_detail,
        }
        for r in rows
    ]
```

- [ ] **Step 4: Add the history route to `router.py`**

```python
# append to control-panel/services/letterboxd/router.py
@router.get("/api/arr/letterboxd/history")
def letterboxd_history(_=Depends(current_user_or_service)):
    from services.letterboxd.sync import recent_sync_logs

    db = SessionLocal()
    try:
        runs = recent_sync_logs(db)
    finally:
        db.close()
    return ok(f"{len(runs)} recent sync run(s).", runs=runs)
```

- [ ] **Step 5: Call `record_sync_log` at the end of `radarr_add_from_letterboxd_list`**

Right before the final `return ok(...)` in the route, add:

```python
    db = SessionLocal()
    try:
        record_sync_log(
            db, payload.url, matched=len(tmdb_ids), unmatched=len(unmatched), added=len(added),
            already=len(already), failed=len(failed), tv_crossover=len(tv_added) + len(tv_already),
        )
    finally:
        db.close()
```

placed after the Task 6 crossover block and before the `summary`/`return ok(...)` lines, and add `from services.letterboxd.sync import record_sync_log` to the top-of-file imports.

- [ ] **Step 6: Run test to verify it passes**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_sync.py tests/control_panel/test_letterboxd_router.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add control-panel/services/letterboxd/sync.py control-panel/services/letterboxd/router.py \
        tests/control_panel/test_letterboxd_sync.py
git commit -m "feat: record + surface Letterboxd sync telemetry (GET /api/arr/letterboxd/history)"
```

---

### Task 8: Tracked lists + diff-only sync-tick endpoint (feature #2, backend half)

Adds registration endpoints (`track`/`untrack`/list) for `LetterboxdTrackedList`, and a `POST /api/arr/letterboxd/sync-tick` endpoint that runs a registered list's add-from-letterboxd-list flow but only reports/adds titles not already recorded as synced for that list (diff, not a full re-add of everything).

**Files:**
- Modify: `control-panel/services/letterboxd/router.py`
- Test: `tests/control_panel/test_letterboxd_router.py` (append)

**Interfaces:**
- Produces: `POST /api/arr/letterboxd/track` (body: `{url, label?, root_folder?, quality_profile?, rating_quality_map?, tags_as_radarr_tags?}`) → `{"ok": true, "message": ..., "id": int}`; `POST /api/arr/letterboxd/untrack` (body: `{url}`) → `{"ok": true, "message": ...}`; `GET /api/arr/letterboxd/tracked` → `{"ok": true, "message": ..., "lists": [{"id", "url", "label", "lastSyncedAt"}]}`; `POST /api/arr/letterboxd/sync-tick` (body: `{}`, no args — runs every tracked list) → `{"ok": true, "message": ..., "results": [{"url", "added", "failed"}]}`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/control_panel/test_letterboxd_router.py
def test_track_untrack_and_list_tracked_letterboxd_lists(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)

    resp = client.post("/api/arr/letterboxd/track", json={"url": "https://letterboxd.com/bear/watchlist/", "label": "Bear's watchlist"})
    assert resp.status_code == 200
    list_id = resp.json()["id"]

    resp = client.get("/api/arr/letterboxd/tracked")
    assert resp.status_code == 200
    lists = resp.json()["lists"]
    assert any(x["id"] == list_id and x["label"] == "Bear's watchlist" for x in lists)

    resp = client.post("/api/arr/letterboxd/untrack", json={"url": "https://letterboxd.com/bear/watchlist/"})
    assert resp.status_code == 200

    resp = client.get("/api/arr/letterboxd/tracked")
    assert resp.json()["lists"] == []


def test_sync_tick_requires_service_key_or_session(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/arr/letterboxd/sync-tick")
    assert resp.status_code == 401


def test_sync_tick_runs_every_tracked_list(cp_main_app, monkeypatch):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    client.post("/api/arr/letterboxd/track", json={"url": "https://letterboxd.com/bear/watchlist/"})

    calls = []

    def fake_run_list_sync(url, **kwargs):
        calls.append(url)
        return {"added": [], "already": [], "failed": [], "unmatched": []}

    monkeypatch.setattr("services.letterboxd.router._run_list_sync", fake_run_list_sync)
    resp = client.post("/api/arr/letterboxd/sync-tick")
    assert resp.status_code == 200
    assert calls == ["https://letterboxd.com/bear/watchlist/"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py::test_track_untrack_and_list_tracked_letterboxd_lists -x -q`
Expected: FAIL (404 — routes don't exist yet)

- [ ] **Step 3: Refactor the add-from-letterboxd-list body into a reusable `_run_list_sync` function**

The existing `radarr_add_from_letterboxd_list` route handler body (all of it, after argument validation) becomes a plain function `_run_list_sync` that both the HTTP route and `sync-tick` call, so tracked-list sync doesn't duplicate the whole flow. In `control-panel/services/letterboxd/router.py`:

```python
def _run_list_sync(url: str, *, monitored: bool = True, search: bool = True, root_folder: str | None = None,
                    quality_profile: str | None = None, limit: int | None = None, dry_run: bool = False,
                    rating_quality_map: dict[str, str] | None = None, tags_as_radarr_tags: bool = False,
                    sonarr_crossover: bool = False) -> dict:
    """Everything radarr_add_from_letterboxd_list's route body did directly
    before this task, now callable from both that route and sync-tick.
    Returns the same fields the route used to build its ok(...) response
    with, as a plain dict (added, already, failed, unmatched, tvAdded,
    tvAlready, tvFailed, matched)."""
    cfg = ARR_APPS["radarr"]
    base_url = url.strip().rstrip("/")
    if LETTERBOXD_DISALLOWED_RE.search(base_url + "/"):
        fail(
            "That URL includes a sort/filter option Letterboxd's robots.txt disallows scraping "
            "(by/, genre/, decade/, year/, this/week/, size/large/, etc). Use the plain, unsorted URL.",
            status_code=400,
        )
    if not LETTERBOXD_GRID_RE.match(base_url):
        fail(
            "Not a recognized Letterboxd list/watchlist/filmography/collection URL - expected something like "
            "https://letterboxd.com/<user>/list/<slug>/, https://letterboxd.com/<user>/watchlist/, "
            "https://letterboxd.com/<user>/films/, https://letterboxd.com/actor/<slug>/, "
            "https://letterboxd.com/films/in/<collection>/, or https://letterboxd.com/films/popular/.",
            status_code=400,
        )
    # ... (the full body from Tasks 2-6, unchanged, just renamed from using
    # `payload.<field>` to using this function's own keyword arguments, and
    # `return {...}` instead of `return ok(...)` at the end) ...
    return {
        "added": added, "already": already, "failed": failed, "unmatched": unmatched,
        "tvAdded": tv_added, "tvAlready": tv_already, "tvFailed": tv_failed,
        "matched": len(tmdb_ids),
    }
```

Update `radarr_add_from_letterboxd_list` to be a thin route wrapper:

```python
@router.post("/api/arr/radarr/add-from-letterboxd-list")
# current_user_or_service, not current_user: stack-letterboxd-radarr-list.fish
# calls this unattended via __stack_api's service key (2026-08-06).
def radarr_add_from_letterboxd_list(payload: LetterboxdListAddRequest, _=Depends(current_user_or_service)):
    result = _run_list_sync(
        payload.url, monitored=payload.monitored, search=payload.search, root_folder=payload.root_folder,
        quality_profile=payload.quality_profile, limit=payload.limit, dry_run=payload.dry_run,
        rating_quality_map=payload.rating_quality_map, tags_as_radarr_tags=payload.tags_as_radarr_tags,
        sonarr_crossover=payload.sonarr_crossover,
    )
    db = SessionLocal()
    try:
        record_sync_log(
            db, payload.url, matched=result["matched"], unmatched=len(result["unmatched"]),
            added=len(result["added"]), already=len(result["already"]), failed=len(result["failed"]),
            tv_crossover=len(result["tvAdded"]) + len(result["tvAlready"]),
        )
    finally:
        db.close()

    verb = "would be added" if payload.dry_run else "added"
    summary = f"{len(result['added'])} {verb}, {len(result['already'])} already in Radarr, {len(result['failed'])} failed"
    if result["unmatched"]:
        summary += f", {len(result['unmatched'])} had no TMDb match"
    if result["tvAdded"] or result["tvAlready"] or result["tvFailed"]:
        summary += (f"; {len(result['tvAdded'])} TV crossover {verb} to Sonarr, "
                     f"{len(result['tvAlready'])} already in Sonarr, {len(result['tvFailed'])} failed")
    return ok(summary, added=result["added"], alreadyCount=len(result["already"]), failed=result["failed"],
              unmatched=result["unmatched"], dryRun=payload.dry_run, tvCrossoverAdded=result["tvAdded"],
              tvCrossoverAlready=result["tvAlready"], tvCrossoverFailed=result["tvFailed"],
              tvCrossoverCount=len(result["tvAdded"]) + len(result["tvAlready"]))
```

- [ ] **Step 4: Add the tracked-list CRUD routes**

```python
# append to control-panel/services/letterboxd/router.py
import json as _json

from models.letterboxd_tracked_list import LetterboxdTrackedList


class TrackRequest(BaseModel):
    url: str
    label: str | None = None
    root_folder: str | None = None
    quality_profile: str | None = None
    rating_quality_map: dict[str, str] | None = None
    tags_as_radarr_tags: bool = False


@router.post("/api/arr/letterboxd/track")
def letterboxd_track(payload: TrackRequest, _=Depends(current_user)):
    db = SessionLocal()
    try:
        existing = db.query(LetterboxdTrackedList).filter_by(url=payload.url).first()
        if existing is not None:
            fail(f"'{payload.url}' is already tracked (id {existing.id}).", status_code=409)
        row = LetterboxdTrackedList(
            url=payload.url, label=payload.label, root_folder=payload.root_folder,
            quality_profile=payload.quality_profile, tags_as_radarr_tags=payload.tags_as_radarr_tags,
            rating_quality_map_json=_json.dumps(payload.rating_quality_map) if payload.rating_quality_map else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return ok(f"Now tracking '{payload.url}'.", id=row.id)
    finally:
        db.close()


class UntrackRequest(BaseModel):
    url: str


@router.post("/api/arr/letterboxd/untrack")
def letterboxd_untrack(payload: UntrackRequest, _=Depends(current_user)):
    db = SessionLocal()
    try:
        row = db.query(LetterboxdTrackedList).filter_by(url=payload.url).first()
        if row is None:
            fail(f"'{payload.url}' isn't tracked.", status_code=404)
        db.delete(row)
        db.commit()
        return ok(f"Stopped tracking '{payload.url}'.")
    finally:
        db.close()


@router.get("/api/arr/letterboxd/tracked")
def letterboxd_tracked(_=Depends(current_user_or_service)):
    db = SessionLocal()
    try:
        rows = db.query(LetterboxdTrackedList).order_by(LetterboxdTrackedList.created_at).all()
        lists = [
            {"id": r.id, "url": r.url, "label": r.label, "lastSyncedAt": r.last_synced_at.isoformat() if r.last_synced_at else None}
            for r in rows
        ]
        return ok(f"{len(lists)} tracked list(s).", lists=lists)
    finally:
        db.close()
```

- [ ] **Step 5: Add the sync-tick route**

```python
# append to control-panel/services/letterboxd/router.py
from datetime import datetime, timezone


@router.post("/api/arr/letterboxd/sync-tick")
# current_user_or_service, not current_user: scripts/letterboxd-sync.py
# (Task 9) calls this unattended via the CONTROL_PANEL_SERVICE_API_KEY,
# same documented automation exception as the other mutating routes in
# this file.
def letterboxd_sync_tick(_=Depends(current_user_or_service)):
    db = SessionLocal()
    try:
        tracked = db.query(LetterboxdTrackedList).all()
        results = []
        for row in tracked:
            rating_quality_map = _json.loads(row.rating_quality_map_json) if row.rating_quality_map_json else None
            try:
                result = _run_list_sync(
                    row.url, root_folder=row.root_folder, quality_profile=row.quality_profile,
                    rating_quality_map=rating_quality_map, tags_as_radarr_tags=row.tags_as_radarr_tags,
                )
                record_sync_log(
                    db, row.url, matched=result["matched"], unmatched=len(result["unmatched"]),
                    added=len(result["added"]), already=len(result["already"]), failed=len(result["failed"]),
                    tv_crossover=len(result["tvAdded"]) + len(result["tvAlready"]),
                )
                row.last_synced_at = datetime.now(timezone.utc)
                db.commit()
                results.append({"url": row.url, "added": result["added"], "failed": result["failed"]})
            except Exception as e:
                record_sync_log(db, row.url, matched=0, unmatched=0, added=0, already=0, failed=0, error_detail=str(e))
                results.append({"url": row.url, "added": [], "failed": [str(e)]})
        return ok(f"Synced {len(tracked)} tracked list(s).", results=results)
    finally:
        db.close()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `/tmp/venv/bin/python3 -m pytest tests/control_panel/test_letterboxd_router.py -q`
Expected: PASS

- [ ] **Step 7: Add `current_user` to the router's imports**

`from core.security import current_user, current_user_or_service` at the top of `router.py` (was only importing `current_user_or_service` before this task).

- [ ] **Step 8: Commit**

```bash
git add control-panel/services/letterboxd/router.py tests/control_panel/test_letterboxd_router.py
git commit -m "feat: tracked-list registration + sync-tick endpoint for scheduled Letterboxd sync"
```

---

### Task 9: Scheduled sync script + systemd timer (feature #2, scheduling half)

**Files:**
- Create: `scripts/letterboxd-sync.py`
- Create: `systemd/stack-letterboxd-sync.service`
- Create: `systemd/stack-letterboxd-sync.timer`
- Test: `tests/scripts/test_letterboxd_sync_script.py`

**Interfaces:**
- Produces: `scripts/letterboxd-sync.py main() -> int` (exit code), calling `POST http://localhost:8420/api/arr/letterboxd/sync-tick` with an `X-Api-Key` header read from `.env`'s `CONTROL_PANEL_SERVICE_API_KEY` — unlike `scripts/poster-sync-fanart.py` (which sends no auth header at all and would 401 against `current_user_or_service`), this script authenticates correctly, matching `fish-functions/__stack_api.fish`'s approach.

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_letterboxd_sync_script.py
import json
import urllib.error
from unittest.mock import MagicMock, patch


def test_main_posts_to_sync_tick_with_service_key(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CONTROL_PANEL_SERVICE_API_KEY=raw-test-key\nOTHER_VAR=ignored\n")
    monkeypatch.setenv("LETTERBOXD_SYNC_ENV_FILE", str(env_file))

    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "letterboxd-sync.py"
    spec = importlib.util.spec_from_file_location("letterboxd_sync_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps({"ok": True, "message": "Synced 2 tracked list(s).",
                                                    "results": [{"url": "a", "added": ["x"], "failed": []}]}).encode()
    fake_response.__enter__ = lambda self: fake_response
    fake_response.__exit__ = lambda self, *a: None

    captured_request = {}

    def fake_urlopen(req, timeout=None):
        captured_request["headers"] = dict(req.header_items())
        captured_request["url"] = req.full_url
        return fake_response

    with patch("urllib.request.urlopen", fake_urlopen):
        exit_code = module.main()

    assert exit_code == 0
    assert captured_request["headers"]["X-api-key"] == "raw-test-key"
    assert captured_request["url"] == "http://localhost:8420/api/arr/letterboxd/sync-tick"


def test_main_returns_1_on_unreachable_control_panel(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CONTROL_PANEL_SERVICE_API_KEY=raw-test-key\n")
    monkeypatch.setenv("LETTERBOXD_SYNC_ENV_FILE", str(env_file))

    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "letterboxd-sync.py"
    spec = importlib.util.spec_from_file_location("letterboxd_sync_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    with patch("urllib.request.urlopen", fake_urlopen):
        exit_code = module.main()

    assert exit_code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/venv/bin/python3 -m pytest tests/scripts/test_letterboxd_sync_script.py -x -q`
Expected: FAIL — `scripts/letterboxd-sync.py` doesn't exist

- [ ] **Step 3: Write the script**

```python
#!/usr/bin/env python3
"""Triggers the diff-only Letterboxd tracked-list sync
(POST /api/arr/letterboxd/sync-tick) and blocks until it returns, so the
systemd unit's exit status is meaningful. Control Panel owns the actual
sync logic (services/letterboxd/router.py's letterboxd_sync_tick) - this
script is just a scriptable, authenticated client of its HTTP API, same
relationship every other scripts/*.py has to the container it drives.

Unlike scripts/poster-sync-fanart.py (which sends no auth header at all),
this script sends the X-Api-Key header that letterboxd_sync_tick's
current_user_or_service dependency requires - the same
CONTROL_PANEL_SERVICE_API_KEY .env value fish-functions/__stack_api.fish
uses for every other unattended stack-* call.

Run by systemd/stack-letterboxd-sync.{service,timer} - nightly.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONTROL_PANEL_URL = "http://localhost:8420"
DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _service_key() -> str | None:
    env_file = Path(os.environ.get("LETTERBOXD_SYNC_ENV_FILE", DEFAULT_ENV_FILE))
    if not env_file.is_file():
        return None
    for line in env_file.read_text().splitlines():
        if line.startswith("CONTROL_PANEL_SERVICE_API_KEY="):
            return line.split("=", 1)[1].strip()
    return None


def main() -> int:
    key = _service_key()
    if not key:
        print(f"No CONTROL_PANEL_SERVICE_API_KEY found in .env - can't authenticate.", file=sys.stderr)
        return 1

    req = urllib.request.Request(
        f"{CONTROL_PANEL_URL}/api/arr/letterboxd/sync-tick", data=b"{}",
        headers={"Content-Type": "application/json", "X-Api-Key": key}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read()).get("detail", {})
        print(f"sync-tick failed: {detail.get('message', str(e))}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"failed to reach Control Panel: {e}", file=sys.stderr)
        return 1

    print(body.get("message"))
    for result in body.get("results", []):
        added = len(result.get("added", []))
        failed = len(result.get("failed", []))
        print(f"  {result['url']}: {added} added, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Make it executable:

```bash
chmod +x scripts/letterboxd-sync.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/tmp/venv/bin/python3 -m pytest tests/scripts/test_letterboxd_sync_script.py -x -q`
Expected: PASS

- [ ] **Step 5: Write the systemd unit files**

```ini
# systemd/stack-letterboxd-sync.service
[Unit]
Description=Diff-only sync of every tracked Letterboxd list to Radarr/Sonarr
After=media-stack.service
OnFailure=notify-failure@%n.service

[Service]
Type=oneshot
WorkingDirectory=/home/bear/Claude/media-stack
ExecStart=/usr/bin/python3 /home/bear/Claude/media-stack/scripts/letterboxd-sync.py
```

```ini
# systemd/stack-letterboxd-sync.timer
[Unit]
Description=Nightly: sync every tracked Letterboxd list to Radarr/Sonarr

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

`04:00:00` deliberately sits between `stack-poster-sync-shows.timer`'s `02:00:00` and `stack-backup.timer`'s `03:30:00` window and `kometa`'s `05:30` in-container run — no overlap with either.

- [ ] **Step 6: Commit**

```bash
git add scripts/letterboxd-sync.py systemd/stack-letterboxd-sync.service systemd/stack-letterboxd-sync.timer \
        tests/scripts/test_letterboxd_sync_script.py
git commit -m "feat: nightly systemd-scheduled sync for tracked Letterboxd lists"
```

- [ ] **Step 7: User step — enable the timer (cannot be done from inside this repo; requires the host's systemd user session)**

This is Bear's step to run on the host, not something the implementing session can do unattended (installing a new systemd user unit takes effect only after a reload+enable, and per this repo's Safety rules, unit installation is a host-level action to confirm, not silently apply). Copy-paste, run from `/home/bear/Claude/media-stack`:

```bash
mkdir -p ~/.config/systemd/user
ln -sf /home/bear/Claude/media-stack/systemd/stack-letterboxd-sync.service ~/.config/systemd/user/stack-letterboxd-sync.service
ln -sf /home/bear/Claude/media-stack/systemd/stack-letterboxd-sync.timer ~/.config/systemd/user/stack-letterboxd-sync.timer
systemctl --user daemon-reload
systemctl --user enable --now stack-letterboxd-sync.timer
systemctl --user list-timers stack-letterboxd-sync.timer
```

Expected final output: a line showing `stack-letterboxd-sync.timer` with a `NEXT` time at or before the next `04:00:00`.

---

### Task 10: Frontend — tracked-list management + sync history panel (feature #2 + #10 UI)

**Files:**
- Create: `control-panel/static/js/letterboxd.js`
- Modify: `control-panel/static/index.html` (add the panel container + script tag)
- Modify: `control-panel/static/commands.json` (register the new endpoints for the existing generic command-runner UI, if that's how this dashboard exposes ad hoc API calls — confirm the file's shape first, see Step 1)

**Interfaces:**
- Consumes: `GET /api/arr/letterboxd/tracked`, `GET /api/arr/letterboxd/history`, `POST /api/arr/letterboxd/track`, `POST /api/arr/letterboxd/untrack`, `POST /api/arr/letterboxd/sync-tick` (Tasks 7, 8).
- Produces: a `#letterboxd-panel` DOM section rendered by `renderLetterboxdPanel()`, called from the existing panel-refresh cycle the same way every other `static/js/*.js` panel is wired (confirm the exact wiring convention in Step 1 before writing new code — do not guess at the pattern).

- [ ] **Step 1: Read the existing wiring convention before writing anything**

Before writing `letterboxd.js`, read `control-panel/static/js/poster-sync.js` (closest analog: it also has a history/status view driven by a Control Panel API) and the relevant `<script>`/panel-registration block in `control-panel/static/index.html` and `control-panel/static/js/core.js` to find the exact convention this dashboard uses for: (a) registering a new panel section, (b) making an authenticated `fetch()` call (session cookie is likely automatic via `credentials: "same-origin"`, but confirm), (c) the CSS classes `style.css` already defines for a data table / status list, so the new panel matches the dashboard's existing look without introducing new CSS patterns.

Run: `grep -n "poster-sync\|renderPosterSync\|DOMContentLoaded\|panel" control-panel/static/js/core.js control-panel/static/index.html | head -40`

Document the exact pattern found (function names, how panels self-register, how `fetch` calls carry auth) as a comment at the top of the new `letterboxd.js` before writing the rest of it, so Task 10 doesn't invent a second, inconsistent panel-wiring convention alongside the existing one.

- [ ] **Step 2: Write `letterboxd.js` following the confirmed convention**

Structure (adapt exact function/registration names to match Step 1's findings):

```javascript
// control-panel/static/js/letterboxd.js
// Panel-wiring convention confirmed against static/js/poster-sync.js and
// static/js/core.js on <date> - see that comment history for what was
// found; this file mirrors it rather than inventing a new pattern.

async function loadLetterboxdTracked() {
  const res = await fetch("/api/arr/letterboxd/tracked", { credentials: "same-origin" });
  const data = await res.json();
  return data.lists || [];
}

async function loadLetterboxdHistory() {
  const res = await fetch("/api/arr/letterboxd/history", { credentials: "same-origin" });
  const data = await res.json();
  return data.runs || [];
}

async function trackLetterboxdList(url, label) {
  const res = await fetch("/api/arr/letterboxd/track", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, label: label || null }),
  });
  return res.json();
}

async function untrackLetterboxdList(url) {
  const res = await fetch("/api/arr/letterboxd/untrack", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  return res.json();
}

function renderLetterboxdPanel(container, tracked, history) {
  const trackedRows = tracked.map(t => `
    <tr>
      <td>${t.label || t.url}</td>
      <td>${t.lastSyncedAt || "never"}</td>
      <td><button data-untrack-url="${t.url}">Untrack</button></td>
    </tr>`).join("");

  const historyRows = history.slice(0, 20).map(r => `
    <tr>
      <td>${r.listUrl}</td>
      <td>${r.runAt}</td>
      <td>${r.added}</td>
      <td>${r.already}</td>
      <td>${r.failed}</td>
      <td>${r.tvCrossover}</td>
      <td>${r.errorDetail || ""}</td>
    </tr>`).join("");

  container.innerHTML = `
    <h3>Tracked Letterboxd Lists</h3>
    <table class="data-table"><thead><tr><th>List</th><th>Last synced</th><th></th></tr></thead>
      <tbody>${trackedRows}</tbody></table>
    <h3>Recent Sync History</h3>
    <table class="data-table"><thead><tr><th>List</th><th>Run at</th><th>Added</th><th>Already</th><th>Failed</th><th>TV crossover</th><th>Error</th></tr></thead>
      <tbody>${historyRows}</tbody></table>`;

  container.querySelectorAll("[data-untrack-url]").forEach(btn => {
    btn.addEventListener("click", async () => {
      await untrackLetterboxdList(btn.dataset.untrackUrl);
      refreshLetterboxdPanel(container);
    });
  });
}

async function refreshLetterboxdPanel(container) {
  const [tracked, history] = await Promise.all([loadLetterboxdTracked(), loadLetterboxdHistory()]);
  renderLetterboxdPanel(container, tracked, history);
}
```

- [ ] **Step 3: Register the panel in `index.html`**

Add a container and script tag matching the exact pattern confirmed in Step 1 (e.g. if every panel is a `<section id="X-panel">` inside a known parent, add `<section id="letterboxd-panel"></section>` in the same place, and `<script src="/js/letterboxd.js"></script>` alongside the other `js/*.js` script tags).

- [ ] **Step 4: Manual browser verification (per this project's UI-change testing requirement)**

Start the stack (if not already running) and load the dashboard in a browser:

```bash
docker compose up -d control-panel
```

Then navigate to `http://192.168.4.20:8420/`, confirm the new Letterboxd panel renders with an empty tracked-list table and empty history table (no tracked lists yet), track a real list via a `curl` call to `/api/arr/letterboxd/track` (using a real session cookie from the logged-in browser, or via `__stack_api` with the service key), reload the dashboard, and confirm the tracked row appears with the correct label and "never" for last-synced.

- [ ] **Step 5: Commit**

```bash
git add control-panel/static/js/letterboxd.js control-panel/static/index.html
git commit -m "feat: dashboard panel for tracked Letterboxd lists + sync history"
```

---

### Task 11: Fish CLI commands

**Files:**
- Modify: `fish-functions/stack-letterboxd-radarr-list.fish` (add new flags)
- Create: `fish-functions/stack-letterboxd-radarr-track.fish`
- Create: `fish-functions/stack-letterboxd-radarr-untrack.fish`
- Create: `fish-functions/stack-letterboxd-radarr-tracked.fish`
- Create: `fish-functions/stack-letterboxd-radarr-history.fish`

**Interfaces:**
- Consumes: `__stack_api` (existing helper, `fish-functions/__stack_api.fish`).

- [ ] **Step 1: Extend `stack-letterboxd-radarr-list.fish` with the new payload fields**

Add `--tags-as-radarr-tags` and `--sonarr-crossover` boolean flags, and a `--rating-quality-map` flag accepting `rating:profile,rating:profile` pairs (e.g. `--rating-quality-map 10:Remux-1080p,2:HD-1080p`), parsed into the `rating_quality_map` JSON object:

```fish
# fish-functions/stack-letterboxd-radarr-list.fish
# Usage: stack-letterboxd-radarr-list <letterboxd-list-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]
#        [--tags-as-radarr-tags] [--sonarr-crossover] [--rating-quality-map rating:profile,rating:profile,...]
function stack-letterboxd-radarr-list --description 'Add every film in a Letterboxd list to Radarr'
    argparse 'no-search' 'no-monitor' 'limit=' 'dry-run' 'tags-as-radarr-tags' 'sonarr-crossover' 'rating-quality-map=' -- $argv
    or return 1
    if test (count $argv) -ne 1
        echo "Usage: stack-letterboxd-radarr-list <letterboxd-list-url> [--no-search] [--no-monitor] [--limit N] [--dry-run] [--tags-as-radarr-tags] [--sonarr-crossover] [--rating-quality-map rating:profile,...]" >&2
        return 1
    end
    set -l url $argv[1]
    set -l search true
    set -l monitored true
    set -l limit 0
    set -l dry_run false
    set -l tags_as_radarr_tags false
    set -l sonarr_crossover false
    set -l rating_map ""
    set -q _flag_no_search; and set search false
    set -q _flag_no_monitor; and set monitored false
    set -q _flag_limit; and set limit $_flag_limit
    set -q _flag_dry_run; and set dry_run true
    set -q _flag_tags_as_radarr_tags; and set tags_as_radarr_tags true
    set -q _flag_sonarr_crossover; and set sonarr_crossover true
    set -q _flag_rating_quality_map; and set rating_map $_flag_rating_quality_map
    set -l body (python3 -c "
import json, sys
url, search, monitored, limit, dry_run, tags, crossover, rating_map = sys.argv[1:9]
payload = {
    'url': url, 'search': search == 'true', 'monitored': monitored == 'true', 'dry_run': dry_run == 'true',
    'tags_as_radarr_tags': tags == 'true', 'sonarr_crossover': crossover == 'true',
}
if int(limit) > 0:
    payload['limit'] = int(limit)
if rating_map:
    pairs = [p.split(':', 1) for p in rating_map.split(',') if ':' in p]
    payload['rating_quality_map'] = {k: v for k, v in pairs}
print(json.dumps(payload))
" "$url" "$search" "$monitored" "$limit" "$dry_run" "$tags_as_radarr_tags" "$sonarr_crossover" "$rating_map")
    __stack_api POST "/api/arr/radarr/add-from-letterboxd-list" "$body"
end
```

- [ ] **Step 2: Write the four new fish functions**

```fish
# fish-functions/stack-letterboxd-radarr-track.fish
# Usage: stack-letterboxd-radarr-track <letterboxd-list-url> [--label TEXT]
function stack-letterboxd-radarr-track --description 'Register a Letterboxd list for nightly diff-only sync'
    argparse 'label=' -- $argv
    or return 1
    if test (count $argv) -ne 1
        echo "Usage: stack-letterboxd-radarr-track <letterboxd-list-url> [--label TEXT]" >&2
        return 1
    end
    set -l url $argv[1]
    set -l label ""
    set -q _flag_label; and set label $_flag_label
    set -l body (python3 -c "
import json, sys
url, label = sys.argv[1:3]
payload = {'url': url}
if label:
    payload['label'] = label
print(json.dumps(payload))
" "$url" "$label")
    __stack_api POST "/api/arr/letterboxd/track" "$body"
end
```

```fish
# fish-functions/stack-letterboxd-radarr-untrack.fish
# Usage: stack-letterboxd-radarr-untrack <letterboxd-list-url>
function stack-letterboxd-radarr-untrack --description 'Stop nightly-syncing a tracked Letterboxd list'
    if test (count $argv) -ne 1
        echo "Usage: stack-letterboxd-radarr-untrack <letterboxd-list-url>" >&2
        return 1
    end
    set -l body (python3 -c "import json, sys; print(json.dumps({'url': sys.argv[1]}))" "$argv[1]")
    __stack_api POST "/api/arr/letterboxd/untrack" "$body"
end
```

```fish
# fish-functions/stack-letterboxd-radarr-tracked.fish
# Usage: stack-letterboxd-radarr-tracked
function stack-letterboxd-radarr-tracked --description 'List every Letterboxd list registered for nightly sync'
    __stack_api GET "/api/arr/letterboxd/tracked"
end
```

```fish
# fish-functions/stack-letterboxd-radarr-history.fish
# Usage: stack-letterboxd-radarr-history
function stack-letterboxd-radarr-history --description 'Show recent Letterboxd sync run history'
    __stack_api GET "/api/arr/letterboxd/history"
end
```

- [ ] **Step 3: User step — deploy the fish functions**

Per `fish-functions/__stack_api.fish`'s own comment, this repo's fish functions are deployed as plain copies at `~/.config/fish/functions/`, not symlinks. Copy-paste, run from `/home/bear/Claude/media-stack`:

```bash
cp fish-functions/stack-letterboxd-radarr-list.fish ~/.config/fish/functions/stack-letterboxd-radarr-list.fish
cp fish-functions/stack-letterboxd-radarr-track.fish ~/.config/fish/functions/stack-letterboxd-radarr-track.fish
cp fish-functions/stack-letterboxd-radarr-untrack.fish ~/.config/fish/functions/stack-letterboxd-radarr-untrack.fish
cp fish-functions/stack-letterboxd-radarr-tracked.fish ~/.config/fish/functions/stack-letterboxd-radarr-tracked.fish
cp fish-functions/stack-letterboxd-radarr-history.fish ~/.config/fish/functions/stack-letterboxd-radarr-history.fish
```

Then reload fish's function cache in any open terminal: `exec fish`

Expected: `stack-letterboxd-radarr-tracked` runs and returns `0 tracked list(s).` (or the current count if some are already tracked from Task 10's manual verification).

- [ ] **Step 4: Commit**

```bash
git add fish-functions/stack-letterboxd-radarr-list.fish fish-functions/stack-letterboxd-radarr-track.fish \
        fish-functions/stack-letterboxd-radarr-untrack.fish fish-functions/stack-letterboxd-radarr-tracked.fish \
        fish-functions/stack-letterboxd-radarr-history.fish
git commit -m "feat: fish CLI commands for Letterboxd tracked-list sync + history"
```

---

### Task 12: Rebuild and deploy the control-panel container

**Files:** none (deployment step only)

- [ ] **Step 1: Rebuild the control-panel image**

```bash
cd /home/bear/Claude/media-stack
docker compose build control-panel
```

- [ ] **Step 2: Recreate the container**

```bash
docker compose up -d --force-recreate control-panel
```

(`--force-recreate` matters here, matching this repo's own documented gotcha about single-file/config-mount staleness — a plain `up -d` won't recreate a container whose compose config hasn't changed, and this task changes code inside the image, not the compose file, so use `build` + `--force-recreate` together, not `up -d --build` alone, which has the same staleness risk if compose sees no config diff.)

- [ ] **Step 3: Confirm health**

```bash
curl -sS http://192.168.4.20:8420/healthz
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Smoke-test one real endpoint**

```bash
stack-letterboxd-radarr-tracked
```

Expected: `0 tracked list(s).` (assuming Task 10's manual browser verification didn't leave a tracked row, or the real count if it did)

---

## Self-Review

**1. Spec coverage** — all six requested features (numbers 1, 2, 3, 4, 9, 10 from the original brainstorm) map to tasks:
- #1 (rating-aware quality mapping) → Task 4
- #2 (scheduled diff-only sync) → Tasks 8 (backend), 9 (scheduling), 10 (UI), 11 (CLI)
- #3 (Sonarr crossover) → Task 6
- #4 (tag scraping) → Task 5
- #9 (dedup-before-scrape cache) → Task 3
- #10 (failure telemetry) → Task 7

Plus the prerequisite fix (Task 0) discovered during research, the extraction refactor that all six features build on (Task 2), models (Task 1), and deployment (Task 12). Every file touched maps to a specific task; nothing is left implicit.

**2. Placeholder scan** — the one intentionally-flagged gap is Task 5 Step 1 (tag markup not independently confirmed live) and Task 10 Step 1 (frontend wiring convention not pre-read) — both are deliberate "verify live, then adjust" steps with concrete verification commands, not unresolved TBDs; they're the correct way to handle "confirmed in the codebase" vs. "needs a live check at implementation time" per this plan's own research-first mandate. No other `TODO`/`TBD`/"add appropriate" phrasing appears.

**3. Type consistency** — traced through: `radarr_add_movie`'s new `tag_ids` parameter (Task 5) is additive/optional, doesn't break Task 3's or Task 4's calls to it. `resolve_tmdb_ids`'s return shape `(list[int], list[str])` (Task 3) is consumed identically in Task 4 (via the `LetterboxdTmdbCache` query) and Task 6 (`unmatched` list feeds `resolve_tv_crossovers`). `_run_list_sync`'s return dict keys (`added`, `already`, `failed`, `unmatched`, `tvAdded`, `tvAlready`, `tvFailed`, `matched`) established in Task 8 Step 3 are used identically by both the HTTP route (Task 8 Step 3) and `sync-tick` (Task 8 Step 5). `LetterboxdSyncLog`'s column names (`matched`, `unmatched`, `added`, `already`, `failed`, `tv_crossover`) match `record_sync_log`'s keyword arguments (Task 7) exactly, and match the JSON keys camelCased consistently in `recent_sync_logs` (Task 7) and the frontend (Task 10).

---

Plan complete and saved to `docs/superpowers/plans/2026-08-06-letterboxd-amplification.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
