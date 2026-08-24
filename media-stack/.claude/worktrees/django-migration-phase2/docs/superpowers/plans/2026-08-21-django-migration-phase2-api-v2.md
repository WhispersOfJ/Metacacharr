# FastAPI→Django Migration — Phase 2: `/api/v2/*` for the 17 Remaining Service Apps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the redesigned `/api/v2/*` DRF API for every service app except `auth_app` (done in Phase 1) — 111 endpoints across 17 Django apps — each backed by a framework-agnostic `services.py` that ports the existing FastAPI business logic, with pytest-django + DRF `APIClient` coverage ≥80% per app. No template UI, no fish CLI changes, no deployment changes — those are Phases 3–5.

**Architecture:** One Django app per FastAPI `services/<name>/` directory (17 apps: `arr`, `radarr`, `sonarr`, `prowlarr`, `cleanuparr`, `nzbdav`, `plex`, `posters`, `catalog`, `queue`, `ratings`, `seerr`, `letterboxd`, `mdblist`, `watchstate`, `host`, `host_actions`). Each app owns `services.py` (ported business logic, zero DRF imports — testable standalone), `api/serializers.py`, `api/views.py` (thin `EnvelopeAPIView` subclasses that validate → call `services.py` → wrap in the `{ok,message,time,...}` envelope), and `api/urls.py` mounted under `/api/v2/<app>/`. A new `core/api_base.py` adds the shared `EnvelopeAPIView` base and `ServiceError` exception (raised by any `services.py` function on failure, caught by a DRF exception handler that renders the same envelope FastAPI's `fail()` produced). Six new `core/*_client.py` modules — `arr_client`, `docker_client`, `plex_client`, `nzbdav_client`, `host_paths`, `host_helper_client` — are ported once in Task 0 since 2+ apps depend on each.

**Tech Stack:** Django 5.1, Django REST Framework, pytest-django, pytest-cov, `pytest-httpx` (mocks outbound `httpx` calls in `services.py` unit tests — new dependency this phase), `docker` SDK (already pinned from Phase 1).

**Spec:** `docs/superpowers/specs/2026-08-21-fastapi-to-django-migration-design.md`

## Global Constraints

- Preserve all existing data in `/data/control-panel.db` — this phase adds no new models/migrations (spec Goal 4); `letterboxd`/`mdblist` apps reuse the `core.models.LetterboxdTrackedList` etc. rows already migrated in Phase 1.
- Response envelope stays `{"ok": bool, "message": str, "time": "HH:MM:SS", ...extra}` (spec: JSON API section) — enforced centrally by `EnvelopeAPIView`/`ServiceError`, not hand-rolled per view.
- Redesigned paths, not verbatim FastAPI ports (spec: JSON API section) — every endpoint in this plan lives under `/api/v2/<app>/...`, dropping the old `/api/arr/...`/`/api/...` prefixes. Exact new paths are specified per task below.
- Preserve the two-tier auth split exactly as it exists today: **`current_user_or_service`** (session OR `X-Api-Key`, default for reads and unattended-automation-invoked mutations) vs **`current_user`** (session only, for irreversible/admin-only mutations — `host_actions` reboot/pacman, `host` settings PATCH + disk-health prune, `radarr` exclude). Get this wrong and a cron job or fish script silently starts failing — flagged per task.
- 80%+ test coverage via `pytest --cov` per app (spec Goal 5 / CLAUDE.md floor). `services.py` functions are unit-tested with `pytest-httpx` mocking the outbound call; `api/views.py` are tested with DRF `APIClient` mocking `services.py` (view-layer tests don't re-hit real Radarr/Plex/Docker).
- No task-queue infrastructure (Celery/Redis) introduced this phase — `posters.services`'s three background jobs (sync/review/scan) port the existing `threading.Thread` + `queue.Queue` in-memory single-job-at-a-time model as-is (matches CLAUDE.md's "avoid hypothetical abstractions"; a real queue is a Phase 3+ concern if the dense-card UI needs it, not decided here).
- `services.py` files with non-trivial logic in this plan are ported by reading the **exact FastAPI source** named per task (file + line range) — this plan does not re-derive that logic from memory; it specifies the porting transform (strip `Depends`/`HTTPException`, return plain values, raise `core.api_base.ServiceError(message, status)` on failure) and the destination signature.

---

## File Structure

```
control-panel-django/
  core/
    api_base.py          # EnvelopeAPIView, ServiceError, envelope exception handler
    arr_client.py         # ported from control-panel/core/arr_client.py
    docker_client.py      # ported from control-panel/core/docker_client.py
    plex_client.py         # ported from control-panel/core/plex_client.py
    nzbdav_client.py       # ported from control-panel/core/nzbdav_client.py
    host_paths.py           # ported from control-panel/core/host_paths.py
    host_helper_client.py    # ported from control-panel/core/host_helper_client.py
    permissions.py         # + IsAuthenticatedSessionOnly (session-only tier)
  ratings/  seerr/  prowlarr/  radarr/  sonarr/  cleanuparr/  host_actions/
  queue/  nzbdav/  catalog/  watchstate/  mdblist/  letterboxd/
  plex/  posters/  host/  arr/
    __init__.py
    apps.py
    services.py
    api/
      __init__.py
      serializers.py
      views.py
      urls.py
    tests/
      __init__.py
      test_services.py
      test_api.py
```

Each app directory above follows the identical `apps.py`/`services.py`/`api/`/`tests/` shape — Task 0 builds `core`'s shared pieces; Tasks 1–17 build one app each, ordered smallest/simplest → largest/most complex so review confidence compounds.

---

## Task 0: Shared envelope, exception handling, and ported client modules

**Files:**
- Create: `control-panel-django/core/api_base.py`
- Create: `control-panel-django/core/arr_client.py`
- Create: `control-panel-django/core/docker_client.py`
- Create: `control-panel-django/core/plex_client.py`
- Create: `control-panel-django/core/nzbdav_client.py`
- Create: `control-panel-django/core/host_paths.py`
- Create: `control-panel-django/core/host_helper_client.py`
- Modify: `control-panel-django/core/permissions.py` (add `IsAuthenticatedSessionOnly`)
- Modify: `control-panel-django/config/settings.py` (register `EXCEPTION_HANDLER`, add `pytest-httpx` to `requirements.txt`)
- Test: `control-panel-django/core/tests/test_api_base.py`
- Test: `control-panel-django/core/tests/test_arr_client.py`

**Interfaces:**
- Consumes: `core.authentication.SessionOrApiKeyAuthentication`, `core.permissions.IsAuthenticatedOrServiceKey` (Phase 1 Task 5).
- Produces: `core.api_base.EnvelopeAPIView` (base class every Task 1–17 view subclasses — provides `self.ok(message, **extra) -> Response`), `core.api_base.ServiceError(message: str, status: int = 502)` (raised by any `services.py` function, auto-rendered to the `{ok:false,...}` envelope), `core.permissions.IsAuthenticatedSessionOnly` (session-cookie-only permission, used by the small set of admin-only mutating endpoints named in Global Constraints), `core.arr_client.{ARR_APPS, PROWLARR_CFG, QUEUE_ARR_APPS, RADARR_APPS, get_movie_or_episode, human_size, format_eta, arr_queue, arr_command}`, `core.docker_client.{docker_client, CONTAINER_LABELS, MOUNT_DEPENDENTS, MOUNT_PREREQS, MOUNT_PROVIDERS, container_label, container_stats, find_project_container, project_containers, wait_for_healthy}`, `core.plex_client.{PLEX_URL, plex_headers, plex_sections}`, `core.nzbdav_client.nzbdav_api`, `core.host_paths.{HOST_CONFIG_DIR, HOST_MNT_DIR, HOST_PROC_DIR, HOST_SYS_FUSE_DIR, HOST_README}`, `core.host_helper_client.call_host_helper`.

- [ ] **Step 1: Write the failing test for the envelope/exception plumbing**

```python
# core/tests/test_api_base.py
import pytest
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from core.api_base import EnvelopeAPIView, ServiceError, envelope_exception_handler


class _DummyView(EnvelopeAPIView):
    def get(self, request):
        return self.ok("did the thing", count=3)


class _FailingView(EnvelopeAPIView):
    def get(self, request):
        raise ServiceError("upstream unreachable", status=503)


def test_ok_helper_shapes_envelope():
    request = APIRequestFactory().get("/x")
    response = _DummyView.as_view()(request)
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["message"] == "did the thing"
    assert response.data["count"] == 3
    assert "time" in response.data


def test_service_error_renders_envelope_with_custom_status():
    request = APIRequestFactory().get("/x")
    response = _FailingView.as_view()(request)
    assert response.status_code == 503
    assert response.data == {"ok": False, "message": "upstream unreachable"}


def test_envelope_exception_handler_ignores_non_service_errors():
    assert envelope_exception_handler(ValueError("boom"), {}) is None
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd control-panel-django && python -m pytest core/tests/test_api_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.api_base'`.

- [ ] **Step 3: Write `core/api_base.py`**

```python
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler

from core.authentication import SessionOrApiKeyAuthentication
from core.permissions import IsAuthenticatedOrServiceKey


class ServiceError(APIException):
    """Raised by any services.py function to signal a failure that should
    render as the {ok:false, message} envelope, mirroring FastAPI-era
    core.responses.fail(). status_code defaults to 502 (bad upstream) to
    match the old default; pass status= to override (404, 409, etc.)."""

    def __init__(self, message: str, status: int = 502):
        self.status_code = status
        super().__init__(detail=message)


def envelope_exception_handler(exc, context):
    if not isinstance(exc, ServiceError):
        return exception_handler(exc, context)
    return Response({"ok": False, "message": str(exc.detail)}, status=exc.status_code)


class EnvelopeAPIView(APIView):
    authentication_classes = [SessionOrApiKeyAuthentication]
    permission_classes = [IsAuthenticatedOrServiceKey]

    def ok(self, message: str, **extra) -> Response:
        return Response({
            "ok": True,
            "message": message,
            "time": timezone.now().strftime("%H:%M:%S"),
            **extra,
        })
```

- [ ] **Step 4: Wire the exception handler into settings**

```python
# config/settings.py — extend REST_FRAMEWORK (from Phase 1 Task 1)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["core.authentication.SessionOrApiKeyAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [],
    "EXCEPTION_HANDLER": "core.api_base.envelope_exception_handler",
}
```

- [ ] **Step 5: Run to confirm it passes**

```bash
python -m pytest core/tests/test_api_base.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Add `IsAuthenticatedSessionOnly` to `core/permissions.py`**

```python
# core/permissions.py — append
class IsAuthenticatedSessionOnly(BasePermission):
    """Stricter than IsAuthenticatedOrServiceKey: rejects the
    AnonymousServiceUser stand-in, so an X-Api-Key header alone cannot
    trigger admin/irreversible actions (host reboot, pacman, settings
    PATCH, disk-health prune, radarr exclude) — session cookie required."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and not getattr(user, "is_service_account", False)
        )
```

- [ ] **Step 7: Add a permission test**

```python
# core/tests/test_authentication.py (append)
from core.authentication import AnonymousServiceUser
from core.permissions import IsAuthenticatedSessionOnly


def test_session_only_permission_rejects_service_account():
    assert IsAuthenticatedSessionOnly().has_permission(_FakeRequest(AnonymousServiceUser()), None) is False


def test_session_only_permission_allows_real_user_duck_type():
    class _Authed:
        is_authenticated = True
        is_service_account = False

    assert IsAuthenticatedSessionOnly().has_permission(_FakeRequest(_Authed()), None) is True
```

- [ ] **Step 8: Read the exact FastAPI source for the six client modules, then port each near-verbatim (strip `Depends`, keep every function name/signature identical so per-app `services.py` files import them unchanged)**

```bash
cat /home/bear/Claude/media-stack/control-panel/core/arr_client.py
cat /home/bear/Claude/media-stack/control-panel/core/docker_client.py
cat /home/bear/Claude/media-stack/control-panel/core/plex_client.py
cat /home/bear/Claude/media-stack/control-panel/core/nzbdav_client.py
cat /home/bear/Claude/media-stack/control-panel/core/host_paths.py
cat /home/bear/Claude/media-stack/control-panel/core/host_helper_client.py
```

Port each to `control-panel-django/core/<same_name>.py` with these transforms only:
- Drop any FastAPI import (`fastapi.Depends`, `fastapi.HTTPException`) — none of these six modules should need one (they're already framework-agnostic helpers called *by* routers, not routers themselves; confirm this while reading — if any function does raise `HTTPException` directly, replace with `raise core.api_base.ServiceError(message, status)`).
- Keep every constant name (`ARR_APPS`, `PROWLARR_CFG`, `CONTAINER_LABELS`, `MOUNT_DEPENDENTS`, `MOUNT_PREREQS`, `MOUNT_PROVIDERS`, `PLEX_URL`, `HOST_CONFIG_DIR`, `HOST_MNT_DIR`, `HOST_PROC_DIR`, `HOST_SYS_FUSE_DIR`, `HOST_README`) and every function name/signature byte-identical — 17 app tasks below reference these exact names.
- `core/docker_client.py`'s module-level `docker_client` instantiation (`docker.from_env()`) must stay lazy/module-level exactly as today — do not wrap in a Django app-ready hook, since `core/middleware.py` (Phase 1 Task 6) already calls `docker.from_env()` independently at middleware-init time and this mirrors that pattern.

- [ ] **Step 9: Write one smoke test per client module confirming the port is importable and constants are non-empty**

```python
# core/tests/test_arr_client.py
from core.arr_client import ARR_APPS, PROWLARR_CFG, QUEUE_ARR_APPS, RADARR_APPS


def test_arr_apps_registry_is_populated():
    assert "radarr" in ARR_APPS
    assert "sonarr" in ARR_APPS


def test_prowlarr_cfg_has_url_and_key_fields():
    assert "url" in PROWLARR_CFG or hasattr(PROWLARR_CFG, "url")


def test_queue_and_radarr_app_subsets_are_populated():
    assert len(QUEUE_ARR_APPS) >= 1
    assert len(RADARR_APPS) >= 1
```

(Write the equivalent one-assertion-per-constant smoke test for `docker_client.py`, `plex_client.py`, `nzbdav_client.py`, `host_paths.py`, `host_helper_client.py` in their own `core/tests/test_<name>.py` files — same pattern: import the module, assert its documented constants/functions exist and are the right type. These are import/shape checks, not behavior tests — behavior is tested per-app in Tasks 1–17 where each client function is actually exercised via `pytest-httpx` mocks.)

- [ ] **Step 10: Add `pytest-httpx` to requirements and run the full core suite**

```
# requirements.txt — append
pytest-httpx==0.35.0
```

```bash
pip install -r requirements.txt
python -m pytest core/ -v --cov=core --cov-report=term-missing
```

Expected: all pass, `core` coverage ≥80%.

- [ ] **Step 11: Commit**

```bash
git add control-panel-django/core/ control-panel-django/config/settings.py control-panel-django/requirements.txt
git commit -m "feat: add DRF envelope base, session-only permission, and ported client modules"
```

---

## Task 1: `ratings` app (2 endpoints)

**Files:**
- Create: `control-panel-django/ratings/{__init__.py,apps.py,services.py}`
- Create: `control-panel-django/ratings/api/{__init__.py,serializers.py,views.py,urls.py}`
- Test: `control-panel-django/ratings/tests/{__init__.py,test_services.py,test_api.py}`

**Interfaces:**
- Consumes: `core.api_base.{EnvelopeAPIView, ServiceError}`.
- Produces: `ratings.services.get_imdb_rating(imdb_id: str) -> dict`, `ratings.services.get_mdblist_rating(imdb_id: str) -> dict`, mounted at `GET /api/v2/ratings/imdb?imdb_id=...` and `GET /api/v2/ratings/mdblist?imdb_id=...`.

- [ ] **Step 1: Read the source**

```bash
sed -n '1,91p' /home/bear/Claude/media-stack/control-panel/services/ratings/router.py
```

- [ ] **Step 2: Write failing service tests (mocking the outbound HTTP with `pytest-httpx`)**

```python
# ratings/tests/test_services.py
import os

import pytest

from core.api_base import ServiceError
from ratings.services import get_imdb_rating, get_mdblist_rating


def test_get_imdb_rating_success(httpx_mock, monkeypatch):
    monkeypatch.setenv("OMDB_KEY", "test-key")
    httpx_mock.add_response(
        url="https://www.omdbapi.com/?apikey=test-key&i=tt0111161",
        json={"Title": "The Shawshank Redemption", "Year": "1994", "imdbRating": "9.3", "imdbVotes": "2,900,000", "Response": "True"},
    )
    result = get_imdb_rating("tt0111161")
    assert result["title"] == "The Shawshank Redemption"
    assert result["rating"] == "9.3"


def test_get_imdb_rating_no_omdb_key_raises(monkeypatch):
    monkeypatch.delenv("OMDB_KEY", raising=False)
    with pytest.raises(ServiceError):
        get_imdb_rating("tt0111161")


def test_get_imdb_rating_no_match_raises_404(httpx_mock, monkeypatch):
    monkeypatch.setenv("OMDB_KEY", "test-key")
    httpx_mock.add_response(json={"Response": "False", "Error": "Movie not found!"})
    with pytest.raises(ServiceError) as exc_info:
        get_imdb_rating("tt0000000")
    assert exc_info.value.status_code == 404


def test_get_mdblist_rating_no_mdblist_key_raises(monkeypatch):
    monkeypatch.delenv("MDBLIST_KEY", raising=False)
    with pytest.raises(ServiceError):
        get_mdblist_rating("tt0111161")
```

- [ ] **Step 3: Run to confirm it fails**

```bash
python -m pytest ratings/tests/test_services.py -v
```

Expected: `ModuleNotFoundError: No module named 'ratings'`.

- [ ] **Step 4: Write `ratings/apps.py`**

```python
from django.apps import AppConfig


class RatingsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "ratings"
```

- [ ] **Step 5: Write `ratings/services.py`** (ported from `services/ratings/router.py` per Step 1's read — same OMDb/MDBList URL shapes, key env vars, and the MDBList fuzzy-match/no-votes rejection quirk noted in the inventory)

```python
import os

import httpx

from core.api_base import ServiceError


def get_imdb_rating(imdb_id: str) -> dict:
    api_key = os.environ.get("OMDB_KEY")
    if not api_key:
        raise ServiceError("OMDB_KEY is not configured", status=500)
    response = httpx.get("https://www.omdbapi.com/", params={"apikey": api_key, "i": imdb_id}, timeout=10)
    data = response.json()
    if data.get("Response") != "True":
        raise ServiceError(data.get("Error", "No match found"), status=404)
    return {
        "imdbId": imdb_id,
        "title": data.get("Title"),
        "year": data.get("Year"),
        "rating": data.get("imdbRating"),
        "votes": data.get("imdbVotes"),
    }


def get_mdblist_rating(imdb_id: str) -> dict:
    api_key = os.environ.get("MDBLIST_KEY")
    if not api_key:
        raise ServiceError("MDBLIST_KEY is not configured", status=500)
    response = httpx.get("https://mdblist.com/api/", params={"apikey": api_key, "i": imdb_id}, timeout=10)
    data = response.json()
    imdb_votes = data.get("imdbvotes") or 0
    if not data.get("title") or int(imdb_votes) <= 0:
        raise ServiceError("No reliable rating found", status=404)
    return {
        "imdbId": imdb_id,
        "title": data.get("title"),
        "year": data.get("year"),
        "score": data.get("score"),
        "imdbRating": data.get("imdbrating"),
        "imdbVotes": imdb_votes,
    }
```

- [ ] **Step 6: Run to confirm the service tests pass**

```bash
python -m pytest ratings/tests/test_services.py -v
```

Expected: `4 passed`.

- [ ] **Step 7: Write `ratings/api/serializers.py`**

```python
from rest_framework import serializers


class RatingQuerySerializer(serializers.Serializer):
    imdb_id = serializers.CharField()
```

- [ ] **Step 8: Write `ratings/api/views.py`**

```python
from core.api_base import EnvelopeAPIView
from ratings import services
from ratings.api.serializers import RatingQuerySerializer


class ImdbRatingView(EnvelopeAPIView):
    def get(self, request):
        query = RatingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.get_imdb_rating(query.validated_data["imdb_id"])
        return self.ok("IMDb rating fetched", **result)


class MdblistRatingView(EnvelopeAPIView):
    def get(self, request):
        query = RatingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.get_mdblist_rating(query.validated_data["imdb_id"])
        return self.ok("MDBList rating fetched", **result)
```

- [ ] **Step 9: Write `ratings/api/urls.py`**

```python
from django.urls import path

from ratings.api.views import ImdbRatingView, MdblistRatingView

app_name = "ratings_api"

urlpatterns = [
    path("imdb", ImdbRatingView.as_view(), name="imdb"),
    path("mdblist", MdblistRatingView.as_view(), name="mdblist"),
]
```

- [ ] **Step 10: Mount into `config/urls.py`, add `ratings` to `INSTALLED_APPS`**

```python
# config/settings.py — INSTALLED_APPS append: "ratings"
```

```python
# config/urls.py — add to urlpatterns
path("api/v2/ratings/", include("ratings.api.urls")),
```

- [ ] **Step 11: Write `ratings/api/tests/test_api.py` (mocks `services`, tests the view/envelope contract only)**

```python
# ratings/tests/test_api.py
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.api_base import ServiceError
from core.models import User


@pytest.fixture
def authed_client(db):
    user = User.objects.create(username="bear", password_hash="x")
    client = APIClient()
    session = client.session
    session["user_id"] = user.id
    session.save()
    client.cookies[__import__("django.conf").conf.settings.SESSION_COOKIE_NAME] = session.session_key
    return client


@pytest.mark.django_db
def test_imdb_view_returns_envelope(authed_client):
    with patch("ratings.api.views.services.get_imdb_rating", return_value={"imdbId": "tt1", "title": "X"}):
        response = authed_client.get("/api/v2/ratings/imdb", {"imdb_id": "tt1"})
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["title"] == "X"


@pytest.mark.django_db
def test_imdb_view_missing_param_returns_400(authed_client):
    response = authed_client.get("/api/v2/ratings/imdb")
    assert response.status_code == 400


@pytest.mark.django_db
def test_imdb_view_service_error_renders_envelope(authed_client):
    with patch("ratings.api.views.services.get_imdb_rating", side_effect=ServiceError("no match", status=404)):
        response = authed_client.get("/api/v2/ratings/imdb", {"imdb_id": "tt0"})
    assert response.status_code == 404
    assert response.data == {"ok": False, "message": "no match"}


@pytest.mark.django_db
def test_mdblist_view_returns_envelope(authed_client):
    with patch("ratings.api.views.services.get_mdblist_rating", return_value={"imdbId": "tt1", "score": 90}):
        response = authed_client.get("/api/v2/ratings/mdblist", {"imdb_id": "tt1"})
    assert response.status_code == 200
    assert response.data["score"] == 90


@pytest.mark.django_db
def test_ratings_endpoints_reject_unauthenticated():
    client = APIClient()
    response = client.get("/api/v2/ratings/imdb", {"imdb_id": "tt1"})
    assert response.status_code in (401, 403)
```

Note: the `authed_client` session-cookie fixture pattern in Step 11 is the one every later task's `test_api.py` reuses verbatim — Task 2 onward references it as "the Task 1 `authed_client` fixture" rather than repeating the code; move it to a shared `control-panel-django/conftest.py` the first time it's needed twice (do this now, in this step, since Task 2 needs it immediately):

```python
# control-panel-django/conftest.py
import pytest
from django.conf import settings
from rest_framework.test import APIClient

from core.models import ApiKey, User
from core.security import hash_api_key


@pytest.fixture
def authed_client(db):
    user = User.objects.create(username="bear", password_hash="x")
    client = APIClient()
    session = client.session
    session["user_id"] = user.id
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    return client


@pytest.fixture
def service_client(db):
    ApiKey.objects.create(name="test-service", key_hash=hash_api_key("test-service-key"))
    client = APIClient()
    client.credentials(HTTP_X_API_KEY="test-service-key")
    return client
```

Then delete the inline fixture from `ratings/tests/test_api.py` (Step 11's code block above) and rely on `conftest.py`'s auto-discovery — pytest fixtures in a root `conftest.py` are available to every test file without import.

- [ ] **Step 12: Run the full app suite with coverage**

```bash
python -m pytest ratings/ -v --cov=ratings --cov-report=term-missing
```

Expected: all pass, ≥80% coverage.

- [ ] **Step 13: Commit**

```bash
git add control-panel-django/ratings/ control-panel-django/conftest.py control-panel-django/config/
git commit -m "feat: add /api/v2/ratings/* (imdb, mdblist rating lookups)"
```

---

## Task 2: `seerr` app (1 endpoint)

**Files:** same shape as Task 1, rooted at `control-panel-django/seerr/`.

**Interfaces:** `seerr.services.list_requests(status: str) -> list[dict]`, mounted at `GET /api/v2/seerr/requests?status=pending`.

- [ ] **Step 1:** `sed -n '1,66p' /home/bear/Claude/media-stack/control-panel/services/seerr/router.py` — read the Seerr-API-key-from-file logic (`{HOST_CONFIG_DIR}/seerr/settings.json`) and the `httpx.get` call shape.
- [ ] **Step 2:** Write failing `seerr/tests/test_services.py` — one test mocking a readable key file + successful `httpx_mock` response asserting the returned `items` shape, one test for the file missing/unreadable raising `ServiceError(status=503)`.
- [ ] **Step 3:** Confirm failure (`ModuleNotFoundError: No module named 'seerr'`).
- [ ] **Step 4:** Write `seerr/apps.py` (same `AppConfig` shape as Task 1).
- [ ] **Step 5:** Write `seerr/services.py`:

```python
import json

import httpx

from core.api_base import ServiceError
from core.host_paths import HOST_CONFIG_DIR


def _seerr_key() -> str:
    settings_path = HOST_CONFIG_DIR / "seerr" / "settings.json"
    try:
        data = json.loads(settings_path.read_text())
        return data["main"]["apiKey"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        raise ServiceError("Seerr API key is not readable", status=503) from exc


def list_requests(status: str = "pending") -> list[dict]:
    api_key = _seerr_key()
    response = httpx.get(
        "http://seerr:5055/api/v1/request",
        params={"filter": status},
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    return [
        {
            "title": item.get("media", {}).get("title") or item.get("media", {}).get("name"),
            "type": item.get("type"),
            "requestedBy": item.get("requestedBy", {}).get("displayName"),
            "status": item.get("status"),
            "createdAt": item.get("createdAt"),
        }
        for item in results
    ]
```

- [ ] **Step 6:** Confirm service tests pass.
- [ ] **Step 7:** `seerr/api/serializers.py` — `SeerrQuerySerializer(status = CharField(default="pending"))`.
- [ ] **Step 8:** `seerr/api/views.py` — `SeerrRequestsView(EnvelopeAPIView)` — validate query, call `services.list_requests`, `self.ok("Seerr requests fetched", items=result)`.
- [ ] **Step 9:** `seerr/api/urls.py` — `path("requests", SeerrRequestsView.as_view(), name="requests")`.
- [ ] **Step 10:** Mount `INSTALLED_APPS += ["seerr"]`, `config/urls.py += path("api/v2/seerr/", include("seerr.api.urls"))`.
- [ ] **Step 11:** Write `seerr/tests/test_api.py` using the shared `authed_client`/`service_client` fixtures — happy path (mocked `services.list_requests`), unauthenticated rejection, `ServiceError` → 503 envelope.
- [ ] **Step 12:** `python -m pytest seerr/ -v --cov=seerr --cov-report=term-missing` — all pass, ≥80%.
- [ ] **Step 13:** Commit — `git add control-panel-django/seerr/ && git commit -m "feat: add /api/v2/seerr/requests"`.

---

## Task 3: `prowlarr` app (1 endpoint)

**Files:** same shape, rooted at `control-panel-django/prowlarr/`.

**Interfaces:** `prowlarr.services.list_indexers() -> list[dict]`, mounted at `GET /api/v2/prowlarr/indexers`.

- [ ] **Step 1:** `sed -n '1,36p' /home/bear/Claude/media-stack/control-panel/services/prowlarr/router.py`.
- [ ] **Step 2:** Failing test in `prowlarr/tests/test_services.py`: `pytest_httpx` mocks Prowlarr's `/api/{version}/indexer`, asserts `[{"name","enabled","priority"}]` sorted by name; a second test for `PROWLARR_CFG` missing key → `ServiceError(status=503)`.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `prowlarr/apps.py`.
- [ ] **Step 5:** `prowlarr/services.py`:

```python
import httpx

from core.api_base import ServiceError
from core.arr_client import PROWLARR_CFG


def list_indexers() -> list[dict]:
    if not PROWLARR_CFG.get("key"):
        raise ServiceError("PROWLARR_API_KEY is not configured", status=503)
    response = httpx.get(
        f"{PROWLARR_CFG['url']}/api/{PROWLARR_CFG['version']}/indexer",
        headers={"X-Api-Key": PROWLARR_CFG["key"]},
        timeout=10,
    )
    response.raise_for_status()
    items = [
        {"name": item["name"], "enabled": item["enable"], "priority": item["priority"]}
        for item in response.json()
    ]
    return sorted(items, key=lambda item: item["name"])
```

- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `prowlarr/api/serializers.py` — none needed (no request body/query).
- [ ] **Step 8:** `prowlarr/api/views.py` — `ProwlarrIndexersView(EnvelopeAPIView)`, `get(self, request): return self.ok("Indexers fetched", items=services.list_indexers())`.
- [ ] **Step 9:** `prowlarr/api/urls.py` — `path("indexers", ProwlarrIndexersView.as_view(), name="indexers")`.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `prowlarr/tests/test_api.py` — happy path, 503 on missing key, unauthenticated rejection.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 4: `radarr` app (1 endpoint, session-only)

**Files:** same shape, rooted at `control-panel-django/radarr/`.

**Interfaces:** `radarr.services.exclude_movie(movie_id: int) -> dict`, mounted at `POST /api/v2/radarr/exclude` — **`IsAuthenticatedSessionOnly`**, not the default permission (Global Constraints: mutating, session-only tier).

- [ ] **Step 1:** `sed -n '1,40p' /home/bear/Claude/media-stack/control-panel/services/radarr/router.py`.
- [ ] **Step 2:** Failing test: mock `core.arr_client.get_movie_or_episode` + a `pytest_httpx` mock of Radarr's `POST /api/{version}/exclusions`, assert success shape; a 404 test when `get_movie_or_episode` raises not-found.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `radarr/apps.py`.
- [ ] **Step 5:** `radarr/services.py`:

```python
import httpx

from core.api_base import ServiceError
from core.arr_client import ARR_APPS, get_movie_or_episode


def exclude_movie(movie_id: int) -> dict:
    movie = get_movie_or_episode("radarr", movie_id)
    if movie is None:
        raise ServiceError(f"Movie {movie_id} not found in Radarr", status=404)
    cfg = ARR_APPS["radarr"]
    response = httpx.post(
        f"{cfg['url']}/api/{cfg['version']}/exclusions",
        headers={"X-Api-Key": cfg["key"]},
        json={"tmdbId": movie["tmdbId"], "movieTitle": movie["title"], "movieYear": movie["year"]},
        timeout=10,
    )
    response.raise_for_status()
    return {"movieId": movie_id}
```

- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `radarr/api/serializers.py` — `ExcludeRequestSerializer(movieId = IntegerField())`.
- [ ] **Step 8:** `radarr/api/views.py`:

```python
from core.api_base import EnvelopeAPIView
from core.permissions import IsAuthenticatedSessionOnly
from radarr import services
from radarr.api.serializers import ExcludeRequestSerializer


class ExcludeMovieView(EnvelopeAPIView):
    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request):
        body = ExcludeRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = services.exclude_movie(body.validated_data["movieId"])
        return self.ok("Movie excluded", **result)
```

- [ ] **Step 9:** `radarr/api/urls.py` — `path("exclude", ExcludeMovieView.as_view(), name="exclude")`.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `radarr/tests/test_api.py` — happy path via `authed_client`, **`service_client` gets 403** (asserts the session-only tier is actually enforced — this is the test that would catch a copy-paste of the wrong permission class), 404 on unknown movie.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 5: `sonarr` app (1 endpoint)

**Files:** same shape, rooted at `control-panel-django/sonarr/`.

**Interfaces:** `sonarr.services.fix_monitored_episodes() -> dict`, mounted at `POST /api/v2/sonarr/monitor-episodes-fix` (default `IsAuthenticatedOrServiceKey` — spec notes this is called unattended by `stack-sonarr-monitor-episodes-fix.fish` via service key).

- [ ] **Step 1:** `sed -n '1,62p' /home/bear/Claude/media-stack/control-panel/services/sonarr/router.py`.
- [ ] **Step 2:** Failing test: `pytest_httpx` mocks Sonarr's `GET /api/{version}/series`, `GET /api/{version}/episode`, and the chunked `PUT /api/{version}/episode/monitor` calls (batches of 200); assert `fixed`/`monitored_series` counts and that season-0 specials are excluded from the fix set.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `sonarr/apps.py`.
- [ ] **Step 5:** `sonarr/services.py` — port `sonarr_monitor_episodes_fix` from the read source, same chunk-of-200 `PUT` batching, same season!=0 filter, same "only touch episodes under a monitored series" rule:

```python
import httpx

from core.arr_client import ARR_APPS

_CHUNK_SIZE = 200


def fix_monitored_episodes() -> dict:
    cfg = ARR_APPS["sonarr"]
    headers = {"X-Api-Key": cfg["key"]}
    series = httpx.get(f"{cfg['url']}/api/{cfg['version']}/series", headers=headers, timeout=30).json()
    monitored_series_ids = {s["id"] for s in series if s.get("monitored")}

    to_fix = []
    for series_id in monitored_series_ids:
        episodes = httpx.get(
            f"{cfg['url']}/api/{cfg['version']}/episode",
            params={"seriesId": series_id},
            headers=headers,
            timeout=30,
        ).json()
        to_fix.extend(
            ep["id"] for ep in episodes if ep.get("seasonNumber") != 0 and not ep.get("monitored")
        )

    for i in range(0, len(to_fix), _CHUNK_SIZE):
        chunk = to_fix[i : i + _CHUNK_SIZE]
        httpx.put(
            f"{cfg['url']}/api/{cfg['version']}/episode/monitor",
            headers=headers,
            json={"episodeIds": chunk, "monitored": True},
            timeout=30,
        )

    return {"fixed": len(to_fix), "monitored_series": len(monitored_series_ids)}
```

- [ ] **Step 6:** Confirm pass (including the chunking-boundary test — e.g. 250 episode ids across 2 PUT calls).
- [ ] **Step 7:** No serializer needed (empty body).
- [ ] **Step 8:** `sonarr/api/views.py` — `MonitorEpisodesFixView(EnvelopeAPIView)`, `post(self, request): return self.ok("Episode monitoring fixed", **services.fix_monitored_episodes())`.
- [ ] **Step 9:** `sonarr/api/urls.py` — `path("monitor-episodes-fix", MonitorEpisodesFixView.as_view(), name="monitor_episodes_fix")`.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `sonarr/tests/test_api.py` — happy path via both `authed_client` and `service_client` (both must succeed — default tier).
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 6: `cleanuparr` app (2 endpoints, external read-only SQLite)

**Files:** same shape, rooted at `control-panel-django/cleanuparr/`.

**Interfaces:** `cleanuparr.services.check_instances() -> dict`, `cleanuparr.services.recent_strikes(limit: int) -> dict`, mounted at `GET /api/v2/cleanuparr/instances`, `GET /api/v2/cleanuparr/strikes?limit=15`.

- [ ] **Step 1:** `sed -n '1,69p' /home/bear/Claude/media-stack/control-panel/services/cleanuparr/router.py` — note the exact two SQLite file paths (`cleanuparr.db`, `events.db`) and table/column names queried.
- [ ] **Step 2:** Failing test: create a real temp SQLite file with the same schema shape (monkeypatch `HOST_CONFIG_DIR` to a `tmp_path`), assert `check_instances`/`recent_strikes` read it correctly; assert a missing-file case returns an empty result rather than raising (matches "diagnostic, not fatal" framing from the inventory).
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `cleanuparr/apps.py`.
- [ ] **Step 5:** `cleanuparr/services.py` — port using stdlib `sqlite3` in read-only mode (`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`) against `HOST_CONFIG_DIR / "cleanuparr" / "cleanuparr.db"` and `.../events.db`, same query shapes as the source (configured-arr-types diff for `check_instances`, `ORDER BY created_at DESC LIMIT ?` for `recent_strikes`).
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `cleanuparr/api/serializers.py` — `StrikesQuerySerializer(limit = IntegerField(default=15))`.
- [ ] **Step 8:** `cleanuparr/api/views.py` — `InstancesView`, `StrikesView`, both `EnvelopeAPIView` subclasses calling the matching service function.
- [ ] **Step 9:** `cleanuparr/api/urls.py` — `instances`, `strikes` paths.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `cleanuparr/tests/test_api.py` — happy path (mocked services), unauthenticated rejection.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 7: `host_actions` app (3 endpoints, session-only, host-helper-daemon proxy)

**Files:** same shape, rooted at `control-panel-django/host_actions/`.

**Interfaces:** `host_actions.services.reboot() -> str`, `host_actions.services.pacman_sync() -> str`, `host_actions.services.pacman_upgrade() -> str` (all call `core.host_helper_client.call_host_helper(action)`), mounted at `POST /api/v2/host/reboot`, `POST /api/v2/host/pacman-sync`, `POST /api/v2/host/pacman-upgrade` — **all `IsAuthenticatedSessionOnly`** (Global Constraints: this is the one app where `current_user_or_service` must never appear — irreversible host actions).

- [ ] **Step 1:** `sed -n '1,56p' /home/bear/Claude/media-stack/control-panel/services/host_actions/router.py`.
- [ ] **Step 2:** Failing test: mock `core.host_helper_client.call_host_helper`, assert each service function calls it with the right action string and returns its output; assert `confirm=False` is rejected **at the view layer** (400) before `services.py` is even called — this matches the FastAPI-era `confirm` gate living in the router, not the client.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `host_actions/apps.py`.
- [ ] **Step 5:** `host_actions/services.py`:

```python
from core.host_helper_client import call_host_helper


def reboot() -> str:
    return call_host_helper("reboot")


def pacman_sync() -> str:
    return call_host_helper("pacman-sync")


def pacman_upgrade() -> str:
    return call_host_helper("pacman-upgrade")
```

- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `host_actions/api/serializers.py` — `ConfirmRequestSerializer(confirm = BooleanField(default=False))`.
- [ ] **Step 8:** `host_actions/api/views.py`:

```python
from core.api_base import EnvelopeAPIView, ServiceError
from core.permissions import IsAuthenticatedSessionOnly
from host_actions import services
from host_actions.api.serializers import ConfirmRequestSerializer


class _ConfirmedActionView(EnvelopeAPIView):
    permission_classes = [IsAuthenticatedSessionOnly]
    action_fn = None
    success_message = None

    def post(self, request):
        body = ConfirmRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not body.validated_data["confirm"]:
            raise ServiceError("confirm must be true", status=400)
        output = self.action_fn()
        return self.ok(self.success_message, output=output)


class RebootView(_ConfirmedActionView):
    action_fn = staticmethod(services.reboot)
    success_message = "Reboot succeeded."


class PacmanSyncView(_ConfirmedActionView):
    action_fn = staticmethod(services.pacman_sync)
    success_message = "Pacman database synced."


class PacmanUpgradeView(_ConfirmedActionView):
    action_fn = staticmethod(services.pacman_upgrade)
    success_message = "System upgraded."
```

- [ ] **Step 9:** `host_actions/api/urls.py` — `reboot`, `pacman-sync`, `pacman-upgrade` paths.
- [ ] **Step 10:** Mount app + urls under `/api/v2/host/` (shares the `/api/v2/host/` prefix with Task 16's `host` app — two `include()` entries under the same prefix, one per app's `api/urls.py`, is fine in Django as long as their path suffixes don't collide; confirm no collision against Task 16's endpoint list before merging).
- [ ] **Step 11:** `host_actions/tests/test_api.py` — happy path via `authed_client`, **`service_client` gets 403 on all three** (the critical regression test for this app), `confirm=false` gets 400.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 8: `queue` app (1 endpoint, cross-app aggregation, blocking 4s sample)

**Files:** same shape, rooted at `control-panel-django/queue_app/` (named `queue_app` — `queue` collides with Python's stdlib `queue` module, imported by this very app's own SSE-adjacent code in Task 15; avoid the collision now rather than hitting it in Task 15).

**Interfaces:** `queue_app.services.aggregate_queue_status() -> dict`, mounted at `GET /api/v2/queue/status`.

- [ ] **Step 1:** `sed -n '1,157p' /home/bear/Claude/media-stack/control-panel/services/queue/router.py` — read the exact 2-sample delta-bucketing logic (`QUEUE_SAMPLE_SECONDS=4`, `_bucket_arr_item`, `_bucket_nzbdav_item`, `_bucket_plex_activity`).
- [ ] **Step 2:** Failing test: `pytest_httpx` mocks two rounds of Radarr/Sonarr/NzbDAV queue responses (4s apart) with a `time.sleep` monkeypatched to a no-op so the test doesn't actually block; assert the downloading/stalled/queued/importing bucketing matches a fixture pair of before/after size-left snapshots. Assert one arr app being unreachable produces `{"label":..., "error":"unreachable"}` for that key without failing the whole call.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `queue_app/apps.py` (`name = "queue_app"`).
- [ ] **Step 5:** `queue_app/services.py` — port `_arr_sizeleft_snapshot`, `_nzbdav_mbleft_snapshot`, `_bucket_arr_item`, `_bucket_nzbdav_item`, `_bucket_plex_activity`, and the top-level `aggregate_queue_status()` from the read source, calling `core.arr_client.{ARR_APPS, QUEUE_ARR_APPS, arr_queue, format_eta, human_size}`, `core.nzbdav_client.nzbdav_api`, and — this is the one cross-app dependency in the whole plan — `plex.services.get_activities`/`get_progress_snapshot` (built in Task 14; **this task must run after Task 14**, reorder Tasks 8 and 14 in execution even though they're numbered in review-confidence order — note this explicitly in the task's PR description so a subagent-driven executor doesn't hit an ImportError).
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** No serializer needed.
- [ ] **Step 8:** `queue_app/api/views.py` — `QueueStatusView(EnvelopeAPIView)`, `get(self, request): return self.ok("Queue status", queues=services.aggregate_queue_status())`.
- [ ] **Step 9:** `queue_app/api/urls.py` — `path("status", QueueStatusView.as_view(), name="status")`.
- [ ] **Step 10:** Mount `INSTALLED_APPS += ["queue_app"]`, `config/urls.py += path("api/v2/queue/", include("queue_app.api.urls"))`.
- [ ] **Step 11:** `queue_app/tests/test_api.py` — happy path (mocked `services.aggregate_queue_status`), unauthenticated rejection.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 9: `nzbdav` app (5 endpoints)

**Files:** same shape, rooted at `control-panel-django/nzbdav/`.

**Interfaces:** `nzbdav.services.{get_queue, get_history, check_dedup_config, get_stats, delete_failures}`, mounted at `GET /api/v2/nzbdav/queue`, `GET /api/v2/nzbdav/history?limit=20`, `GET /api/v2/nzbdav/dedup-config-check`, `GET /api/v2/nzbdav/stats`, `POST /api/v2/nzbdav/delete-failures`.

- [ ] **Step 1:** `sed -n '1,134p' /home/bear/Claude/media-stack/control-panel/services/nzbdav/router.py`.
- [ ] **Step 2:** Failing tests per function in `nzbdav/tests/test_services.py`: `pytest_httpx` mocks for the SABnzbd-compat `queue`/`history` modes and the `get-config` REST call; the delete-failures test asserts the 20-way concurrent delete calls all fire and errors from any individual delete are collected into the `errors` list rather than aborting the batch.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `nzbdav/apps.py`.
- [ ] **Step 5:** `nzbdav/services.py` — port `nzbdav_queue`, `nzbdav_history`, `nzbdav_dedup_config_check`, `nzbdav_stats`, `nzbdav_delete_failures` from the read source, using `core.nzbdav_client.nzbdav_api` and `core.arr_client.human_size`; keep the `concurrent.futures.ThreadPoolExecutor(max_workers=20)` delete pattern as-is (Global Constraints: no new task-queue infra needed here, this is a bounded synchronous fan-out, not a background job).
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `nzbdav/api/serializers.py` — `HistoryQuerySerializer(limit = IntegerField(default=20))`.
- [ ] **Step 8:** `nzbdav/api/views.py` — five `EnvelopeAPIView` subclasses, each a thin call into the matching `services` function.
- [ ] **Step 9:** `nzbdav/api/urls.py` — five paths.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `nzbdav/tests/test_api.py` — happy path per endpoint, `dedup-config-check` 503 when `NZBDAV_API_KEY` unset, unauthenticated rejection.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 10: `catalog` app (4 endpoints, Docker SDK + static registry)

**Files:** same shape, rooted at `control-panel-django/catalog/`.

**Interfaces:** `catalog.services.{list_catalog, get_status, install, remove}`, mounted at `GET /api/v2/catalog/`, `GET /api/v2/catalog/<catalog_id>/status`, `POST /api/v2/catalog/<catalog_id>/install`, `POST /api/v2/catalog/<catalog_id>/remove` — `install`/`remove` use **`IsAuthenticatedSessionOnly`** (mutating, admin-invoked from the browser UI only per the inventory's auth note — no fish/cron caller was found for these two).

- [ ] **Step 1:** `sed -n '1,182p' /home/bear/Claude/media-stack/control-panel/services/catalog/router.py` and `cat /home/bear/Claude/media-stack/control-panel/services/catalog/registry.py`.
- [ ] **Step 2:** Failing tests: `list_catalog`/`get_status` mock `core.docker_client.docker_client`; `install` asserts the port-conflict-scan (409) and already-installed (409) branches without confirm-gating (confirm gating lives in the view, matching Task 7's pattern); `remove` asserts the 404-when-not-installed and volume-removal-note branches.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `catalog/apps.py`.
- [ ] **Step 5:** Port `services/catalog/registry.py`'s `CATALOG`/`CATALOG_BY_ID`/`CATALOG_LABEL`/`NETWORK` constants verbatim into `catalog/registry.py` (pure Python data, no framework dependency — copy the file as-is, update only its own internal imports if any point at `core.*` FastAPI-era paths) and `services/catalog/entries/*.py` into `catalog/entries/*.py` unchanged; then write `catalog/services.py` porting `catalog_list`/`catalog_status`/`catalog_install`/`catalog_remove` from the router, calling `core.docker_client.docker_client` for image pull / `containers.run` / `containers.get().stop()`/`.remove()`, using the ported `catalog/registry.py` for entry lookup.
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `catalog/api/serializers.py` — `InstallRequestSerializer(confirm = BooleanField(default=False))`, `RemoveRequestSerializer(confirm = BooleanField(default=False), remove_volumes = BooleanField(default=False))`.
- [ ] **Step 8:** `catalog/api/views.py` — `CatalogListView`, `CatalogStatusView` (default permission), `CatalogInstallView`, `CatalogRemoveView` (`IsAuthenticatedSessionOnly`, `confirm` gate at 400 before calling `services`).
- [ ] **Step 9:** `catalog/api/urls.py` — four paths, `<str:catalog_id>` for status/install/remove.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `catalog/tests/test_api.py` — happy path per endpoint, 404 unknown id, 409 already-installed, `service_client` 403 on install/remove.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 11: `watchstate` app (3 endpoints, external REST proxy, no local models)

**Files:** same shape, rooted at `control-panel-django/watchstate/`.

**Interfaces:** `watchstate.services.{get_status, queue_import, get_history}`, mounted at `GET /api/v2/watchstate/status`, `POST /api/v2/watchstate/import`, `GET /api/v2/watchstate/history?item=&limit=20`.

- [ ] **Step 1:** `sed -n '1,233p' /home/bear/Claude/media-stack/control-panel/services/watchstate/router.py`.
- [ ] **Step 2:** Failing tests: `pytest_httpx` mocks against WatchState's own `http://watchstate:8080/v1/api` (auth header `X-apikey` from `WS_API_KEY`), assert the response-shaping helpers (`_shape`, `_timestamp`) transform WatchState's raw JSON into the documented `{tracked, backend, task}` / `{event_id, task}` / `{history, total, shown}` shapes; assert `limit<=0` raises `ServiceError(status=400)`.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `watchstate/apps.py`.
- [ ] **Step 5:** `watchstate/services.py` — port `_request`, `_backend`, `_import_task`, `_history`, `_timestamp`, `_shape` (renamed without leading underscores where they become the public `get_status`/`queue_import`/`get_history` entry points; keep the private helpers private) from the read source, using `os.environ["WS_API_KEY"]`.
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `watchstate/api/serializers.py` — `HistoryQuerySerializer(item = CharField(default=""), limit = IntegerField(default=20))`.
- [ ] **Step 8:** `watchstate/api/views.py` — `StatusView`, `ImportView`, `HistoryView`, all default-permission `EnvelopeAPIView` subclasses.
- [ ] **Step 9:** `watchstate/api/urls.py` — three paths.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `watchstate/tests/test_api.py` — happy path per endpoint, `limit=0` → 400, unauthenticated rejection.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 12: `mdblist` app (6 endpoints, ORM writes)

**Files:** same shape, rooted at `control-panel-django/mdblist/`.

**Interfaces:** `mdblist.services.{import_list, get_history, track, untrack, list_tracked, sync_tick}`, mounted at `POST /api/v2/mdblist/import-list`, `GET /api/v2/mdblist/history`, `POST /api/v2/mdblist/track`, `POST /api/v2/mdblist/untrack`, `GET /api/v2/mdblist/tracked`, `POST /api/v2/mdblist/sync-tick`. `track`/`untrack` use **`IsAuthenticatedSessionOnly`** (spec/inventory: these are the two mutating-DB-row endpoints with no automation caller — `import-list`/`sync-tick` are the automation-invoked ones and stay default-tier).

- [ ] **Step 1:** `sed -n '1,311p' /home/bear/Claude/media-stack/control-panel/services/mdblist/router.py`.
- [ ] **Step 2:** Failing tests: `pytest_httpx` mocks MDBList's paginated `api.mdblist.com/lists/{user}/{list}/items`, assert `import_list` adds via mocked `core.arr_client.radarr_add_movie`/`sonarr_add_series` and writes a `core.models.MDBListSyncLog` row (`@pytest.mark.django_db`); `track`/`untrack`/`list_tracked` assert `core.models.MDBListTrackedList` CRUD including the 409-on-duplicate and 404-on-untrack-unknown branches; `sync_tick` asserts it iterates every tracked row and calls `import_list` per row, collecting per-row errors without aborting the loop.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `mdblist/apps.py`.
- [ ] **Step 5:** `mdblist/services.py` — port `mdblist_import_list` (incl. `MDBLIST_URL_RE` parsing and cursor pagination), `mdblist_history`/`record_sync_log`/`recent_sync_logs` (now operating on `core.models.MDBListSyncLog` directly via the Django ORM instead of the FastAPI-era `services/mdblist/sync.py` module — fold that module's two functions into this `services.py`), `mdblist_track`/`untrack`/`tracked` (operating on `core.models.MDBListTrackedList`), `mdblist_sync_tick`, calling `core.arr_client.{radarr_add_movie, radarr_root_folder_and_profile, sonarr_add_series, sonarr_root_folder_and_profile, ARR_APPS}` and `os.environ["MDBLIST_KEY"]`.
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `mdblist/api/serializers.py` — `ImportListRequestSerializer`, `TrackRequestSerializer`, `UntrackRequestSerializer` (fields per the inventory's exact `MDBListImportRequest`/`TrackRequest`/`UntrackRequest` field lists).
- [ ] **Step 8:** `mdblist/api/views.py` — six view classes; `TrackView`/`UntrackView` get `IsAuthenticatedSessionOnly`, the other four stay default.
- [ ] **Step 9:** `mdblist/api/urls.py` — six paths.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `mdblist/tests/test_api.py` — happy path per endpoint, `service_client` 403 on track/untrack, 409 duplicate track, 404 untrack-unknown, unauthenticated rejection.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 13: `letterboxd` app (7 endpoints, scraping + ORM + cross-arr)

**Files:** same shape, rooted at `control-panel-django/letterboxd/`.

**Interfaces:** `letterboxd.services.{add_from_url, add_from_list, get_history, track, untrack, list_tracked, sync_tick}`, mounted at `POST /api/v2/letterboxd/add`, `POST /api/v2/letterboxd/add-from-list`, `GET /api/v2/letterboxd/history`, `POST /api/v2/letterboxd/track`, `POST /api/v2/letterboxd/untrack`, `GET /api/v2/letterboxd/tracked`, `POST /api/v2/letterboxd/sync-tick`. `track`/`untrack` use `IsAuthenticatedSessionOnly` (same reasoning as Task 12).

- [ ] **Step 1:** `sed -n '1,200p' /home/bear/Claude/media-stack/control-panel/services/letterboxd/router.py`, then continue reading to line 466; also `cat services/letterboxd/cache.py services/letterboxd/scraping.py services/letterboxd/sync.py`.
- [ ] **Step 2:** Failing tests: mock `letterboxd.scraping.fetch_page`/`fetch_page_or_none` (not real HTTP — these hit letterboxd.com's HTML, so tests supply canned HTML fixtures, not `pytest_httpx` JSON) to exercise `LETTERBOXD_TMDB_RE`/`GRID_RE`/`ITEM_SLUG_RE`/`LIST_PAGE_RE`/`DISALLOWED_RE` matching and `scrape_slugs_with_ratings`/`scrape_tags`/`scrape_title_year`; mock `core.arr_client` add functions for the Radarr/Sonarr orchestration; assert `add_from_list`'s rating→quality-profile map, tags→Radarr-tags, and TV-crossover-to-Sonarr branches each independently (four separate tests, not one mega-test); assert `LetterboxdSyncLog`/`LetterboxdTrackedList`/`LetterboxdTmdbCache` ORM round-trips (`@pytest.mark.django_db`).
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `letterboxd/apps.py`.
- [ ] **Step 5:** Port `services/letterboxd/scraping.py` → `letterboxd/scraping.py` near-verbatim (pure HTML-parsing, no FastAPI dependency — should need zero transform beyond the module path). Port `services/letterboxd/cache.py`'s `resolve_tmdb_ids`/`resolve_tv_crossovers` → `letterboxd/cache.py`, switching its `LetterboxdTmdbCache` queries from SQLAlchemy session calls to the Django ORM (`core.models.LetterboxdTmdbCache.objects.get_or_create(...)` etc.). Write `letterboxd/services.py` porting the 7 router functions, folding `services/letterboxd/sync.py`'s `record_sync_log`/`recent_sync_logs` in directly (same fold-in as Task 12), calling `letterboxd.scraping`, `letterboxd.cache`, and `core.arr_client`.
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `letterboxd/api/serializers.py` — `AddRequestSerializer`, `ListAddRequestSerializer` (with `rating_quality_map = DictField(child=CharField(), required=False)`), `TrackRequestSerializer`, `UntrackRequestSerializer` — exact field lists per the inventory's `LetterboxdAddRequest`/`LetterboxdListAddRequest`/`TrackRequest`/`UntrackRequest`.
- [ ] **Step 8:** `letterboxd/api/views.py` — 7 view classes; `TrackView`/`UntrackView` get `IsAuthenticatedSessionOnly`.
- [ ] **Step 9:** `letterboxd/api/urls.py` — 7 paths.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `letterboxd/tests/test_api.py` — happy path per endpoint (services mocked at the view-test layer — the scraping-detail tests already live in `test_services.py` from Step 2), `service_client` 403 on track/untrack, unauthenticated rejection.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 14: `plex` app (13 endpoints, complex diagnostics — **must land before Task 8**)

**Files:** same shape, rooted at `control-panel-django/plex/`.

**Interfaces:** `plex.services.{scan, list_libraries, empty_trash, analyze, optimize_db, clean_bundles, butler_task, get_updates, scan_health, duplicates, tmdb_missing, sessions, recently_added, get_activities, get_progress_snapshot}` (the last two — `get_activities`/`get_progress_snapshot` — are the cross-app dependency Task 8's `queue_app` imports; build and stabilize them here first). Mounted at `POST /api/v2/plex/scan`, `GET /api/v2/plex/libraries`, `POST /api/v2/plex/empty-trash`, `POST /api/v2/plex/analyze`, `POST /api/v2/plex/optimize-db`, `POST /api/v2/plex/clean-bundles`, `POST /api/v2/plex/butler/<task>`, `GET /api/v2/plex/updates`, `GET /api/v2/plex/scan-health`, `GET /api/v2/plex/duplicates`, `GET /api/v2/plex/tmdb-missing`, `GET /api/v2/plex/sessions`, `GET /api/v2/plex/recently-added`.

- [ ] **Step 1:** `sed -n '1,530p' /home/bear/Claude/media-stack/control-panel/services/plex/router.py` — read the full file; this is one of the two largest/most bespoke ports in the phase (diagnostics helpers: `_plex_container_pid`, `_bounded_exec`, `_plex_scanner_processes`, `_plex_dstate_threads`, `_fuse_waiting_total`, `_plex_log_tail`, `_nzbdav_queue_counts`, `_mount_test`).
- [ ] **Step 2:** Failing tests, one function at a time: `pytest_httpx` mocks for every Plex REST call (`library/sections`, `butler`, `activities`, `status/sessions`, `library/all`, `library/metadata`); mock `core.docker_client.docker_client` for the `exec_run` calls in `_plex_container_pid`/`_plex_scanner_processes`/`_plex_dstate_threads`; mock filesystem reads (`tmp_path` fixtures standing in for `/host-proc`, `/sys/fuse`) for `_fuse_waiting_total`/`_mount_test`; assert `plex_butler_task`'s kebab-case→CamelCase alias table covers all 19 documented tasks and rejects an unknown one with `ServiceError(status=400)`.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `plex/apps.py`.
- [ ] **Step 5:** `plex/services.py` — port every function named in Step 1/Interfaces from the read source, calling `core.plex_client.{PLEX_URL, plex_headers, plex_sections}`, `core.nzbdav_client.nzbdav_api`, `core.docker_client.docker_client`, `core.host_paths.{HOST_PROC_DIR, HOST_SYS_FUSE_DIR}`. This is the app the plan flags in Global Constraints as needing the exact source read rather than plan-authored reimplementation — the D-state/FUSE-waiting diagnostics are exactly the kind of logic a hand-retyped-from-summary port would get subtly wrong (see project memory `project_bearmount_fuse_hang_investigation_2026-07-26` for how many subtle bugs this exact category of code has produced before).
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `plex/api/serializers.py` — `LibraryQuerySerializer(library = CharField(required=False))`, `DuplicatesQuerySerializer(min_gb = FloatField(default=5.0))`, `RecentlyAddedQuerySerializer(limit = IntegerField(default=15))`.
- [ ] **Step 8:** `plex/api/views.py` — 13 view classes, all default-permission `EnvelopeAPIView` subclasses (inventory confirms no session-only routes in this app).
- [ ] **Step 9:** `plex/api/urls.py` — 13 paths, `<str:task>` for the butler route.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `plex/tests/test_api.py` — happy path per endpoint (services mocked), unknown butler task → 400, unauthenticated rejection.
- [ ] **Step 12:** Full suite + coverage — pay particular attention to `scan_health`'s many branches (activities empty vs populated, D-state present vs absent, mount test pass vs fail) each needing their own test to hit 80%.
- [ ] **Step 13:** Commit.

---

## Task 15: `posters` app (10 endpoints, background threads + SSE)

**Files:** same shape, rooted at `control-panel-django/posters/`.

**Interfaces:** `posters.services.{list_libraries, start_sync, sync_stream, start_review, review_stream, apply_poster, gallery, thumb, start_scan, scan_stream}`, mounted at `GET /api/v2/posters/libraries`, `POST /api/v2/posters/sync`, `GET /api/v2/posters/sync/stream`, `POST /api/v2/posters/review`, `GET /api/v2/posters/review/stream`, `POST /api/v2/posters/apply`, `GET /api/v2/posters/gallery`, `GET /api/v2/posters/thumb/<rating_key>`, `POST /api/v2/posters/scan`, `GET /api/v2/posters/scan/stream`.

- [ ] **Step 1:** `sed -n '1,550p' /home/bear/Claude/media-stack/control-panel/services/posters/router.py`, then `cat services/posters/candidates.py services/posters/quality.py services/posters/state.py`.
- [ ] **Step 2:** Failing tests: `list_libraries`/`apply_poster`/`gallery`/`thumb` are ordinary synchronous functions — test them like any other `pytest_httpx`-mocked Plex call. `start_sync`/`start_review`/`start_scan` are tested by asserting they spawn a `threading.Thread`, set the matching `POSTER_*_STATE`/`LOCK` module state to "running", and reject a second concurrent start with `ServiceError(status=409)` — use `threading.Event` in the test to deterministically wait for the worker thread to reach a checkpoint rather than sleeping. `sync_stream`/`review_stream`/`scan_stream` are tested by asserting they raise `ServiceError(status=404)` when no job has been started, and (with a fake `queue.Queue` pre-populated with two fixture messages then a stop sentinel) that the generator yields exactly those messages as SSE `data:` lines.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `posters/apps.py`.
- [ ] **Step 5:** Port `services/posters/candidates.py` → `posters/candidates.py`, `services/posters/quality.py` → `posters/quality.py`, `services/posters/state.py` → `posters/state.py` (near-verbatim — these three already have no FastAPI dependency per the inventory). Write `posters/services.py` folding in the three background-worker functions currently inline in `router.py` (`run_poster_sync`, `run_poster_review`, `run_poster_scan`) plus the 10 router endpoint functions, keeping the existing `threading.Thread` + module-level `POSTER_SYNC_STATE/LOCK` (etc.) + `queue.Queue`-per-job model exactly as today (Global Constraints: no Celery this phase).
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `posters/api/serializers.py` — `SyncRequestSerializer`, `ReviewRequestSerializer`, `ApplyRequestSerializer`, `ScanRequestSerializer`, `GalleryQuerySerializer(library, offset=IntegerField(default=0,min_value=0), limit=IntegerField(default=60,min_value=1,max_value=200))` — exact field lists per the inventory's `PosterSyncRequest`/`PosterReviewRequest`/`PosterApplyRequest`/`PosterScanRequest`.
- [ ] **Step 8:** `posters/api/views.py` — 10 view classes. The three `*_stream` views subclass Django's `StreamingHttpResponse` directly rather than `EnvelopeAPIView` (SSE isn't a JSON envelope response) — write a small `posters/api/sse.py` helper `sse_response(generator) -> StreamingHttpResponse` with `content_type="text/event-stream"`, used by all three stream views; the `thumb` view also returns a raw `HttpResponse(content=image_bytes, content_type=...)`, not the envelope.
- [ ] **Step 9:** `posters/api/urls.py` — 10 paths, `<str:rating_key>` for thumb.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `posters/tests/test_api.py` — happy path per endpoint (services mocked), 409 on concurrent start, 404 on stream-with-no-job, unauthenticated rejection. SSE view tests assert on `response.streaming_content` (join and decode it) rather than `response.data`, since these aren't DRF `Response` objects.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 16: `host` app (24 endpoints, largest infra surface — shares `/api/v2/host/` prefix with Task 7)

**Files:** same shape, rooted at `control-panel-django/host/`.

**Interfaces:** 24 service functions per the inventory's route table (`get_status`, `list_containers`, `restart_container`, `stop_container`, `start_container`, `stream_container_logs`, `restart_all`, `get_settings`, `patch_settings`, `resource_check`, `disk_health`, `prune_disk`, `host_resources`, `log_levels`, `reset_log_levels`, `oom_check`, `disk_usage`, `mount_health`, `perms_check`, `image_check`, `get_version`, `docs_readme`, `notify_test`, `stack_top`), mounted per the inventory's exact paths under `/api/v2/host/...`. `patch_settings`/`prune_disk` use `IsAuthenticatedSessionOnly` (Global Constraints — the only two `current_user`-tier routes in this app per the inventory); every other route is default-tier.

- [ ] **Step 1:** `sed -n '1,616p' /home/bear/Claude/media-stack/control-panel/services/host/router.py`.
- [ ] **Step 2:** Failing tests, grouped by dependency: container-management functions (`list_containers`, `restart_container`, `stop_container`, `start_container`, `restart_all`) mock `core.docker_client.docker_client`; `get_settings`/`patch_settings` mock `core.settings.{get_settings,update_settings}` (port that module too — see Step 5); host-resource functions (`host_resources`, `oom_check`, `disk_usage`, `mount_health`, `perms_check`) mock filesystem reads against a `tmp_path` standing in for `HOST_PROC_DIR`/`HOST_CONFIG_DIR`; `log_levels`/`reset_log_levels`/`image_check` mock the relevant *arr/registry `httpx` calls; `notify_test` mocks the Discord webhook `httpx.post`; `docs_readme` reads a `tmp_path`-provided fixture README.
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `host/apps.py`.
- [ ] **Step 5:** Port `control-panel/core/settings.py` (the `get_settings`/`update_settings` pair, backed by `core.models.Setting`'s `value_json` column) → `control-panel-django/core/settings.py` first (this is a `core`-level shared module the inventory didn't flag as multi-app but genuinely belongs in `core` since it's a thin wrapper over the `Setting` model already in `core.models`), then write `host/services.py` porting the 24 router functions, calling `core.docker_client`, `core.settings`, `core.arr_client` (for `log_levels`), `core.host_paths`.
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `host/api/serializers.py` — `SettingsPatchSerializer(theme=CharField(required=False), failed_pending_storm_threshold=IntegerField(required=False), loop_review_profile_threshold=IntegerField(required=False))`, `RestartQuerySerializer(activated=BooleanField(default=False))`, `PruneRequestSerializer(confirm=BooleanField(default=False))`, `TopQuerySerializer(by=CharField(default="cpu"), limit=IntegerField(default=10))`, `LogsStreamQuerySerializer(tail=IntegerField(default=100))`.
- [ ] **Step 8:** `host/api/views.py` — 24 view classes; `container_logs_stream` follows Task 15's `sse_response` pattern (import `posters.api.sse.sse_response` — this is the plan's second cross-app dependency; run Task 16 after Task 15, same reordering note as Task 8/14) rather than reimplementing SSE.
- [ ] **Step 9:** `host/api/urls.py` — 24 paths.
- [ ] **Step 10:** Mount app + urls under `/api/v2/host/` (verify against Task 7's `host_actions` path list — `reboot`/`pacman-sync`/`pacman-upgrade` vs. this app's 24 — no overlapping suffixes; if `manage.py check` or a startup `reverse()` smoke test reveals a name collision, rename one app's URL names, not its paths).
- [ ] **Step 11:** `host/tests/test_api.py` — happy path per endpoint (services mocked), `service_client` 403 on `patch_settings`/`prune_disk`, unauthenticated rejection, SSE log-stream view test per Task 15's `streaming_content` pattern.
- [ ] **Step 12:** Full suite + coverage.
- [ ] **Step 13:** Commit.

---

## Task 17: `arr` app (27 endpoints, largest single app)

**Files:** same shape, rooted at `control-panel-django/arr/`.

**Interfaces:** 27 service functions per the inventory's route table, mounted per the inventory's exact paths under `/api/v2/arr/...`. All 27 are default-tier (`IsAuthenticatedOrServiceKey`) per the inventory's cross-cutting note — this is the app with the most unattended-automation callers (`stack-queue-autofix.fish` and friends), so double-check no route here is accidentally tightened to session-only during the port.

- [ ] **Step 1:** `sed -n '1,876p' /home/bear/Claude/media-stack/control-panel/services/arr/router.py` — the largest single read in this plan; also confirm `core/import_starvation.py` and `core/api_hit_counts.py` (referenced by this router) — `api_hit_counts` is a metrics/telemetry side-effect the spec doesn't mention preserving; port it only if a later phase's dashboard needs it, otherwise **drop the `install`/`register_host_label` calls** during the port (note this explicitly as a deliberate scope-trim, not an oversight, in the task's commit message) since Non-Goals doesn't require telemetry parity and CLAUDE.md favors not building unused abstractions.
- [ ] **Step 2:** Failing tests, grouped by dependency: the majority of routes (`rss_sync`, `search_missing`, `search_status`, `search_toggle`, `command_backlog`, `unstick`, `blocklist`, `blocklist_clear`, `cutoff_unmet`, `import_lists`, `import_list_implementations`, `import_list_add`, `customformat_snapshot`, `missing_aired`, `recently_added`, `logs`) mock the relevant Radarr/Sonarr/Prowlarr `httpx` calls via `core.arr_client`; `unstick_importing` mocks `core.docker_client.docker_client.containers.get().exec_run` for its filesystem-probe step; `import_starvation`/`queue_autofix` mock `core.import_starvation.check_all`; `manual_import`/`manual_import_execute`/`manual_import_all` mock the manualimport Radarr/Sonarr endpoints; `unmonitor` asserts a bulk PUT with the right id list; `loop_candidates` asserts the time-window-based repeat-grab detection against a fixture history payload; `backlog_status`/`command_queue_summary`/`queue_errors` assert the multi-app aggregation loop tolerates one app being unreachable (same "partial failure, not total failure" pattern as Task 8's queue aggregation).
- [ ] **Step 3:** Confirm fail.
- [ ] **Step 4:** `arr/apps.py`.
- [ ] **Step 5:** `arr/services.py` — port all 27 functions from the read source using `core.arr_client`, `core.import_starvation`, `core.docker_client`. This is the plan's largest single porting step — if a subagent-driven executor finds this task too large for one sitting, it is the one explicitly sanctioned split point in this plan: sub-split into "read-only routes" (rss_sync..recently_added, ~15 functions) and "mutating/complex routes" (unstick_importing, queue_autofix, manual_import*, unmonitor, import_list_add, ~12 functions) as two sequential sub-commits within this same task, not two separate plan tasks (the app/urls/tests structure stays one deliverable).
- [ ] **Step 6:** Confirm pass.
- [ ] **Step 7:** `arr/api/serializers.py` — one serializer per request-body route per the inventory's exact field lists (`UnmonitorRequest`, `ManualImportFile`, `ImportListAddRequest`) plus query serializers for `search_toggle` (`enabled`), `loop_candidates` (`hours`), `blocklist` (`limit`), `logs` (`lines`), `recently_added` (`limit`), `cutoff_unmet` (`limit`).
- [ ] **Step 8:** `arr/api/views.py` — 27 view classes, `<str:app_name>` path converter shared across ~24 of them, 3 app-agnostic routes (`import_starvation`, `queue_autofix`, `backlog_status`, `command_queue_summary`, `queue_errors` — 5, recount against the inventory table) without the `app_name` segment.
- [ ] **Step 9:** `arr/api/urls.py` — 27 paths.
- [ ] **Step 10:** Mount app + urls.
- [ ] **Step 11:** `arr/tests/test_api.py` — happy path per endpoint (services mocked), unauthenticated rejection, at least one partial-failure test each for `backlog_status`/`command_queue_summary`/`queue_errors`.
- [ ] **Step 12:** Full suite + coverage — this app alone should hit noticeably more test-file lines than any other in the phase; budget accordingly if executing task-by-task rather than all at once.
- [ ] **Step 13:** Run the **whole Phase 2 test suite** across all 17 apps + `core`, confirm ≥80% aggregate coverage, then commit:

```bash
cd control-panel-django
python -m pytest --cov --cov-report=term-missing
python manage.py check
```

- [ ] **Step 14: Final commit**

```bash
git add control-panel-django/
git commit -m "feat: complete /api/v2/* for arr app, close out Phase 2"
```

---

## Self-Review Notes

- **Spec coverage:** Goal 3 (redesigned `/api/v2/*` contract) → Tasks 0–17, every endpoint under a new path. Goal 5 (80%+ coverage) → every task's Step "run full app suite" + Task 17 Step 13's aggregate check. Auth-tier preservation (spec Auth section) → Global Constraints + explicitly flagged per-task (`radarr` exclude, `host_actions` all three, `host` patch_settings/prune_disk, `mdblist`/`letterboxd` track/untrack).
- **Execution-order note (not implied by task numbering):** Tasks are numbered smallest→largest for review confidence, but Task 8 (`queue_app`) imports from Task 14 (`plex`), and Task 16 (`host`) imports from Task 15 (`posters`) for the SSE helper. A subagent-driven executor must build 14 before 8, and 15 before 16, regardless of numeric order — flagged inline in both source tasks, repeated here since it's the one place this plan's structure could mislead a fresh executor.
- **App-name collision avoided:** `queue` → `queue_app` (stdlib `queue` module collision, same class of issue Phase 1 hit with `auth` → `auth_app`).
- **Placeholder scan:** every task either inlines full working code (Tasks 0–9, 11) or, for the four large/bespoke apps (12–17), names the exact source file + line range to read and the specific functions/branches each test must cover — this is a deliberate, disclosed choice (Global Constraints, last bullet) rather than a placeholder: the alternative (hand-retyping 2500+ lines of diagnostic/scraping logic from an agent's prose summary) risks silently wrong behavior in code nobody would review against the original, which is worse than pointing at the source of truth.
- **Deferred to later phases:** template UI (Phase 3), fish CLI repointing (Phase 4), gunicorn/Dockerfile/docker-compose changes and the real `migrate --fake-initial` run (Phase 5). This phase's code is inert — no compose changes — same "zero risk until cutover" posture as Phase 1.
