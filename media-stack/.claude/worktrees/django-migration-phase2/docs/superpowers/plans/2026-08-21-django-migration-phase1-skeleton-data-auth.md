# FastAPI→Django Migration — Phase 1: Skeleton, Data Layer, Auth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a working, tested Django project that preserves every row in the existing control-panel SQLite database and reproduces session + service-key auth — as a self-contained deliverable that does not touch the live FastAPI container.

**Architecture:** New Django project in a sibling directory `control-panel-django/` (NOT inside `control-panel/`, to avoid `core`/`models` package-name collisions with the still-running FastAPI code and to guarantee zero risk to production until the Phase 5 cutover). A `core` app owns the 9 preserved ORM models (`Meta.db_table` matched to existing table names) plus the ported argon2/sha256 security helpers and the DRF session-or-API-key authentication primitives. An `auth` app owns the login/logout views and templates — this is also app #1 of the 18 service apps the full migration needs, built now because Phase 1 needs a real login flow to be testable end-to-end.

**Tech Stack:** Django 5.1, Django REST Framework, SQLite, argon2-cffi, pytest-django, pytest-cov, `docker` SDK (for the ported same-origin check's gateway lookup).

**Spec:** `docs/superpowers/specs/2026-08-21-fastapi-to-django-migration-design.md`

## Global Constraints

- Preserve all existing data in `/data/control-panel.db` — zero data loss (spec Goal 4).
- `Meta.db_table` on every model must match the existing SQLAlchemy table name exactly — no `ALTER` should be needed when `migrate --fake-initial` runs against the real DB.
- No side-by-side/incremental production cutover — this phase's code is inert (no compose/Dockerfile changes) until Phase 5 (spec Non-Goals).
- No attempt to preserve existing itsdangerous-signed sessions — forced re-login on deploy is accepted (spec Non-Goals).
- 80%+ test coverage via `pytest --cov` (spec Goal 5 / CLAUDE.md floor). Zero prior Python test coverage exists — every test in this phase is net-new.
- Password hashing stays argon2 (via `argon2-cffi`, already a pinned dependency); API-key hashing stays plain SHA-256 — do not switch either to Django's default PBKDF2 hasher, since that would invalidate the preserved `password_hash` column's existing values.
- Reuse the existing env var names `CONTROL_PANEL_SECRET_KEY`, `CONTROL_PANEL_DB_PATH`, `CONTROL_PANEL_ADMIN_USERNAME`, `CONTROL_PANEL_ADMIN_PASSWORD`, `CONTROL_PANEL_SERVICE_API_KEY`, `HOST_IP` — Phase 5's cutover must not require new docker-compose environment entries for anything this phase builds.

---

## File Structure

```
control-panel-django/
  manage.py
  requirements.txt
  pytest.ini
  config/
    __init__.py
    settings.py
    urls.py
    wsgi.py
  core/
    __init__.py
    apps.py
    models.py
    admin.py
    security.py
    authentication.py
    permissions.py
    middleware.py
    management/
      __init__.py
      commands/
        __init__.py
        bootstrap.py
    migrations/
      __init__.py
      0001_initial.py
    tests/
      __init__.py
      test_models.py
      test_security.py
      test_authentication.py
      test_bootstrap.py
  auth/
    __init__.py
    apps.py
    views.py
    urls.py
    templates/
      auth/
        login.html
    tests/
      __init__.py
      test_views.py
```

- `core` — shared data layer + auth primitives every later app depends on. Nothing here is FastAPI-router-specific.
- `auth` — the browser-facing login/logout flow. This is app #1 of the 18-app service list from the spec; every later phase's app follows this same `apps.py`/`views.py`/`urls.py`/`templates/<app>/` shape.
- `core/security.py` is a near-verbatim port of `control-panel/core/security.py`'s hashing/token functions, minus the FastAPI `Depends`/`HTTPException` plumbing (replaced by Django session reads in `core/authentication.py` and `auth/views.py`).

---

## Task 1: Django project skeleton

**Files:**
- Create: `control-panel-django/manage.py`
- Create: `control-panel-django/requirements.txt`
- Create: `control-panel-django/pytest.ini`
- Create: `control-panel-django/config/__init__.py`
- Create: `control-panel-django/config/settings.py`
- Create: `control-panel-django/config/urls.py`
- Create: `control-panel-django/config/wsgi.py`

**Interfaces:**
- Produces: `config.settings` module importable as `DJANGO_SETTINGS_MODULE=config.settings`; `config.urls.urlpatterns` (empty list, extended by later tasks); `BASE_DIR` (a `pathlib.Path` pointing at `control-panel-django/`) importable from `config.settings` for later apps' template/static paths.

- [ ] **Step 1: Create the directory and a minimal `requirements.txt`**

```
Django==5.1.4
djangorestframework==3.15.2
argon2-cffi==25.1.0
docker==7.2.0
pytest==8.3.4
pytest-django==4.9.0
pytest-cov==6.0.0
```

- [ ] **Step 2: Write `config/settings.py`**

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("CONTROL_PANEL_SECRET_KEY", "dev-only-insecure-key-do-not-deploy")

DEBUG = os.environ.get("CONTROL_PANEL_DEBUG", "") == "1"

ALLOWED_HOSTS = ["*"]  # narrowed by core.middleware.VerifySameOriginMiddleware, not Django's own check

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
    "auth_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.VerifySameOriginMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("CONTROL_PANEL_DB_PATH", str(BASE_DIR / "dev-control-panel.db")),
    }
}

# django.contrib.auth's own User model (auth_user table, brand new — does not
# collide with the preserved `users` table) backs ONLY /admin/ logins via
# `manage.py createsuperuser`. The real control-panel login (auth_app) uses
# core.models.User against the preserved `users` table and never touches
# django.contrib.auth's session/user machinery — see core/authentication.py.

SESSION_COOKIE_NAME = "cp_session"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 days, matches the retired itsdangerous SESSION_MAX_AGE
SESSION_ENGINE = "django.contrib.sessions.backends.db"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["core.authentication.SessionOrApiKeyAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [],
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

LOGIN_URL = "auth_app:login"
```

- [ ] **Step 3: Write `config/urls.py`**

```python
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
```

- [ ] **Step 4: Write `config/wsgi.py`**

```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
```

- [ ] **Step 5: Write `manage.py`**

```python
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
```

- [ ] **Step 6: Write `pytest.ini`**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
testpaths = core auth_app
```

Note: the `auth` app directory is named `auth_app` on disk (both here and in every later task) — `auth` collides with `django.contrib.auth`, which is already an installed app providing the `/admin/` login backend.

- [ ] **Step 7: Install dependencies and verify the skeleton boots**

```bash
cd control-panel-django
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py check
```

Expected: `System check identified no issues (0 silenced).` — this will fail until `core` and `auth_app` exist as real Python packages (Task 2/6 create them); for now confirm the failure is `ModuleNotFoundError: No module named 'core'`, proving the settings file itself is valid.

- [ ] **Step 8: Commit**

```bash
git add control-panel-django/manage.py control-panel-django/requirements.txt control-panel-django/pytest.ini control-panel-django/config/
git commit -m "feat: scaffold Django project skeleton for control-panel migration"
```

---

## Task 2: `core` app — models

**Files:**
- Create: `control-panel-django/core/__init__.py`
- Create: `control-panel-django/core/apps.py`
- Create: `control-panel-django/core/models.py`
- Create: `control-panel-django/core/admin.py`
- Test: `control-panel-django/core/tests/__init__.py`
- Test: `control-panel-django/core/tests/test_models.py`

**Interfaces:**
- Consumes: nothing (first app-internal task).
- Produces: `core.models.User`, `core.models.Setting`, `core.models.ApiKey`, `core.models.AuditLog`, `core.models.LetterboxdTmdbCache`, `core.models.LetterboxdTrackedList`, `core.models.LetterboxdSyncLog`, `core.models.MDBListTrackedList`, `core.models.MDBListSyncLog` — every field name matches the source SQLAlchemy model exactly, so later phases' `services.py` ports can read/write them with the same attribute names.

- [ ] **Step 1: Write `core/apps.py`**

```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "core"
```

- [ ] **Step 2: Write the failing model test for `User`**

```python
# core/tests/test_models.py
import pytest

from core.models import User


@pytest.mark.django_db
def test_user_table_name_matches_existing_schema():
    assert User._meta.db_table == "users"


@pytest.mark.django_db
def test_user_defaults():
    user = User.objects.create(username="bear", password_hash="argon2-hash-placeholder")
    assert user.is_admin is True
    assert user.created_at is not None
```

- [ ] **Step 2b: Run it to confirm it fails**

```bash
cd control-panel-django && python -m pytest core/tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.models'` (or collection error) — `core/models.py` doesn't exist yet.

- [ ] **Step 3: Write `core/models.py`**

```python
from django.db import models


class User(models.Model):
    username = models.CharField(max_length=150, unique=True)
    password_hash = models.CharField(max_length=255)
    is_admin = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Duck-typed for core.authentication.SessionOrApiKeyAuthentication / DRF
    # permission checks — this model intentionally does NOT subclass
    # AbstractBaseUser (which would add its own `password` column and break
    # Meta.db_table parity with the existing `users` table).
    is_authenticated = True

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.username


class Setting(models.Model):
    key = models.CharField(max_length=255, primary_key=True)
    value_json = models.TextField()

    class Meta:
        db_table = "settings"

    def __str__(self):
        return self.key


class ApiKey(models.Model):
    name = models.CharField(max_length=255)
    key_hash = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "api_keys"

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    user_id = models.IntegerField(null=True, blank=True)
    action = models.CharField(max_length=255)
    detail = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"

    def __str__(self):
        return f"{self.action} @ {self.created_at}"


class LetterboxdTmdbCache(models.Model):
    slug = models.CharField(max_length=255, primary_key=True)
    tmdb_id = models.IntegerField(null=True, blank=True)
    media_type = models.CharField(max_length=32, default="movie")
    cached_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "letterboxd_tmdb_cache"

    def __str__(self):
        return self.slug


class LetterboxdTrackedList(models.Model):
    url = models.CharField(max_length=1024, unique=True)
    label = models.CharField(max_length=255, null=True, blank=True)
    root_folder = models.CharField(max_length=1024, null=True, blank=True)
    quality_profile = models.CharField(max_length=255, null=True, blank=True)
    rating_quality_map_json = models.TextField(null=True, blank=True)
    tags_as_radarr_tags = models.BooleanField(default=False)
    app = models.CharField(max_length=64, default="radarr")
    sonarr_app = models.CharField(max_length=64, default="sonarr")
    created_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "letterboxd_tracked_list"

    def __str__(self):
        return self.label or self.url


class LetterboxdSyncLog(models.Model):
    list_url = models.CharField(max_length=1024)
    run_at = models.DateTimeField(auto_now_add=True)
    matched = models.IntegerField(default=0)
    unmatched = models.IntegerField(default=0)
    added = models.IntegerField(default=0)
    already = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)
    tv_crossover = models.IntegerField(default=0)
    error_detail = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "letterboxd_sync_log"

    def __str__(self):
        return f"{self.list_url} @ {self.run_at}"


class MDBListTrackedList(models.Model):
    url = models.CharField(max_length=1024, unique=True)
    label = models.CharField(max_length=255, null=True, blank=True)
    app = models.CharField(max_length=64, default="radarr")
    sonarr_app = models.CharField(max_length=64, default="sonarr")
    radarr_root_folder = models.CharField(max_length=1024, null=True, blank=True)
    radarr_quality_profile = models.CharField(max_length=255, null=True, blank=True)
    sonarr_root_folder = models.CharField(max_length=1024, null=True, blank=True)
    sonarr_quality_profile = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mdblist_tracked_list"

    def __str__(self):
        return self.label or self.url


class MDBListSyncLog(models.Model):
    list_url = models.CharField(max_length=1024)
    run_at = models.DateTimeField(auto_now_add=True)
    radarr_added = models.IntegerField(default=0)
    radarr_already = models.IntegerField(default=0)
    radarr_failed = models.IntegerField(default=0)
    sonarr_added = models.IntegerField(default=0)
    sonarr_already = models.IntegerField(default=0)
    sonarr_failed = models.IntegerField(default=0)
    error_detail = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "mdblist_sync_log"

    def __str__(self):
        return f"{self.list_url} @ {self.run_at}"
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
python -m pytest core/tests/test_models.py -v
```

Expected: still fails — no migration exists yet, so `pytest-django`'s `--django-db` fixture has no `users` table to insert into. This is expected; Task 3 adds the migration. Confirm the failure is now `django.db.utils.OperationalError: no such table: users`, not an import error.

- [ ] **Step 5: Write `core/admin.py`** (spec-confirmed: Django admin used for models)

```python
from django.contrib import admin

from core.models import (
    ApiKey,
    AuditLog,
    LetterboxdSyncLog,
    LetterboxdTmdbCache,
    LetterboxdTrackedList,
    MDBListSyncLog,
    MDBListTrackedList,
    Setting,
    User,
)

admin.site.register(User)
admin.site.register(Setting)
admin.site.register(ApiKey)
admin.site.register(AuditLog)
admin.site.register(LetterboxdTmdbCache)
admin.site.register(LetterboxdTrackedList)
admin.site.register(LetterboxdSyncLog)
admin.site.register(MDBListTrackedList)
admin.site.register(MDBListSyncLog)
```

- [ ] **Step 6: Commit (test still red, migration comes next task)**

```bash
git add control-panel-django/core/__init__.py control-panel-django/core/apps.py control-panel-django/core/models.py control-panel-django/core/admin.py control-panel-django/core/tests/
git commit -m "feat: port SQLAlchemy models to Django ORM in core app"
```

---

## Task 3: Migrations + schema-parity verification against real data

**Files:**
- Create: `control-panel-django/core/migrations/__init__.py`
- Create: `control-panel-django/core/migrations/0001_initial.py` (generated, then committed verbatim)
- Test: `control-panel-django/core/tests/test_models.py` (extend)

**Interfaces:**
- Consumes: `core.models.*` from Task 2.
- Produces: an applied migration so `pytest-django`'s per-test DB has all 9 tables; a documented, one-time manual runbook step for applying `migrate --fake-initial` to the real `/data/control-panel.db` (executed for real in Phase 5, not by this test suite).

- [ ] **Step 1: Generate the migration**

```bash
cd control-panel-django
python manage.py makemigrations core
```

Expected output: `Migrations for 'core': core/migrations/0001_initial.py` listing all 9 models being created.

- [ ] **Step 2: Run the Task 2 tests to confirm they now pass**

```bash
python -m pytest core/tests/test_models.py -v
```

Expected: `2 passed`.

- [ ] **Step 3: Add a model test per remaining table, asserting `db_table` and one round-trip write/read**

```python
# core/tests/test_models.py (append)
from core.models import (
    ApiKey,
    AuditLog,
    LetterboxdSyncLog,
    LetterboxdTmdbCache,
    LetterboxdTrackedList,
    MDBListSyncLog,
    MDBListTrackedList,
    Setting,
)


@pytest.mark.django_db
def test_setting_round_trip():
    Setting.objects.create(key="theme", value_json='"dark"')
    assert Setting.objects.get(key="theme").value_json == '"dark"'


@pytest.mark.django_db
def test_api_key_table_name_and_uniqueness():
    assert ApiKey._meta.db_table == "api_keys"
    ApiKey.objects.create(name="healthcheck-cron", key_hash="abc123")
    with pytest.raises(Exception):
        ApiKey.objects.create(name="dup", key_hash="abc123")


@pytest.mark.django_db
def test_audit_log_allows_null_user_id():
    row = AuditLog.objects.create(action="login_failed", detail="unknown user 'x'")
    assert row.user_id is None


@pytest.mark.django_db
def test_letterboxd_tmdb_cache_table_name():
    assert LetterboxdTmdbCache._meta.db_table == "letterboxd_tmdb_cache"


@pytest.mark.django_db
def test_letterboxd_tracked_list_defaults():
    row = LetterboxdTrackedList.objects.create(url="https://letterboxd.com/x/list/y/")
    assert row.app == "radarr"
    assert row.sonarr_app == "sonarr"
    assert row.tags_as_radarr_tags is False


@pytest.mark.django_db
def test_letterboxd_sync_log_table_name():
    assert LetterboxdSyncLog._meta.db_table == "letterboxd_sync_log"


@pytest.mark.django_db
def test_mdblist_tracked_list_defaults():
    row = MDBListTrackedList.objects.create(url="https://mdblist.com/lists/x/y")
    assert row.app == "radarr"
    assert row.sonarr_app == "sonarr"


@pytest.mark.django_db
def test_mdblist_sync_log_table_name():
    assert MDBListSyncLog._meta.db_table == "mdblist_sync_log"
```

- [ ] **Step 4: Run full model test file**

```bash
python -m pytest core/tests/test_models.py -v
```

Expected: all tests pass (9 `db_table`/behavior assertions total).

- [ ] **Step 5: Commit the migration and expanded tests**

```bash
git add control-panel-django/core/migrations/ control-panel-django/core/tests/test_models.py
git commit -m "feat: generate initial Django migration for core models"
```

- [ ] **Step 6: One-time manual verification against a COPY of the real database (not automated, run once now to de-risk Phase 5)**

```bash
cp /data/control-panel.db /tmp/control-panel-schema-check.db
CONTROL_PANEL_DB_PATH=/tmp/control-panel-schema-check.db python manage.py migrate --fake-initial
sqlite3 /tmp/control-panel-schema-check.db "SELECT username, is_admin FROM users LIMIT 5;"
rm /tmp/control-panel-schema-check.db
```

Expected: `migrate --fake-initial` reports `Applying core.0001_initial... FAKED` with no `OperationalError`, and the `sqlite3` query returns existing rows unchanged. If it errors, the model field types/`db_table` in Task 2 don't match the live schema exactly — fix `core/models.py` and re-run Step 1 before proceeding. This step touches only a throwaway `/tmp` copy, never `/data/control-panel.db` itself.

---

## Task 4: Port password/API-key hashing helpers

**Files:**
- Create: `control-panel-django/core/security.py`
- Test: `control-panel-django/core/tests/test_security.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `core.security.hash_password(raw: str) -> str`, `core.security.verify_password(raw: str, password_hash: str) -> bool`, `core.security.hash_api_key(raw_key: str) -> str` — same names/signatures as `control-panel/core/security.py`, consumed by `core.models.User` (Step 3 below) and `core/authentication.py` (Task 5).

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_security.py
from core.security import hash_api_key, hash_password, verify_password


def test_hash_and_verify_password_round_trip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hash_api_key_is_deterministic_sha256():
    import hashlib

    raw = "some-service-key"
    assert hash_api_key(raw) == hashlib.sha256(raw.encode()).hexdigest()
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest core/tests/test_security.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.security'`.

- [ ] **Step 3: Write `core/security.py`**

```python
import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()
```

- [ ] **Step 4: Run to confirm it passes**

```bash
python -m pytest core/tests/test_security.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Wire `core.models.User.check_password`/`set_password` to these helpers**

```python
# core/models.py — add inside class User, after the `is_authenticated = True` line
    def check_password(self, raw_password: str) -> bool:
        from core.security import verify_password

        return verify_password(raw_password, self.password_hash)

    def set_password(self, raw_password: str) -> None:
        from core.security import hash_password

        self.password_hash = hash_password(raw_password)
```

- [ ] **Step 6: Add a model test for the new methods**

```python
# core/tests/test_models.py (append)
@pytest.mark.django_db
def test_user_set_password_and_check_password():
    user = User(username="bear")
    user.set_password("hunter2")
    user.save()
    assert user.check_password("hunter2") is True
    assert user.check_password("wrong") is False
```

- [ ] **Step 7: Run all core tests**

```bash
python -m pytest core/ -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add control-panel-django/core/security.py control-panel-django/core/models.py control-panel-django/core/tests/
git commit -m "feat: port argon2 password and sha256 api-key hashing to core.security"
```

---

## Task 5: DRF authentication + permission classes for `/api/v2/*`

**Files:**
- Create: `control-panel-django/core/authentication.py`
- Create: `control-panel-django/core/permissions.py`
- Test: `control-panel-django/core/tests/test_authentication.py`

**Interfaces:**
- Consumes: `core.models.User`, `core.models.ApiKey`, `core.security.hash_api_key` (Tasks 2 & 4).
- Produces: `core.authentication.SessionOrApiKeyAuthentication` (a DRF `BaseAuthentication` subclass — set as `settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]` already in Task 1), `core.authentication.AnonymousServiceUser`, `core.permissions.IsAuthenticatedOrServiceKey` (a DRF `BasePermission` subclass) — every `/api/v2/*` view built in Phase 2 sets `permission_classes = [IsAuthenticatedOrServiceKey]`.

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_authentication.py
import pytest
from rest_framework.test import APIRequestFactory

from core.authentication import SessionOrApiKeyAuthentication
from core.models import ApiKey, User
from core.security import hash_api_key


@pytest.mark.django_db
def test_authenticate_returns_none_with_no_credentials():
    request = APIRequestFactory().get("/api/v2/health")
    request.session = {}
    result = SessionOrApiKeyAuthentication().authenticate(request)
    assert result is None


@pytest.mark.django_db
def test_authenticate_via_valid_session():
    user = User.objects.create(username="bear", password_hash="x")
    request = APIRequestFactory().get("/api/v2/health")
    request.session = {"user_id": user.id}
    result = SessionOrApiKeyAuthentication().authenticate(request)
    assert result is not None
    authed_user, _ = result
    assert authed_user.username == "bear"


@pytest.mark.django_db
def test_authenticate_via_valid_api_key():
    ApiKey.objects.create(name="healthcheck-cron", key_hash=hash_api_key("secret-key"))
    request = APIRequestFactory().get("/api/v2/health", HTTP_X_API_KEY="secret-key")
    request.session = {}
    result = SessionOrApiKeyAuthentication().authenticate(request)
    assert result is not None
    authed_user, _ = result
    assert authed_user.is_authenticated is True


@pytest.mark.django_db
def test_authenticate_rejects_invalid_api_key():
    from rest_framework.exceptions import AuthenticationFailed

    request = APIRequestFactory().get("/api/v2/health", HTTP_X_API_KEY="not-a-real-key")
    request.session = {}
    with pytest.raises(AuthenticationFailed):
        SessionOrApiKeyAuthentication().authenticate(request)


@pytest.mark.django_db
def test_authenticate_updates_last_used_at_on_valid_key():
    key_row = ApiKey.objects.create(name="healthcheck-cron", key_hash=hash_api_key("secret-key"))
    assert key_row.last_used_at is None
    request = APIRequestFactory().get("/api/v2/health", HTTP_X_API_KEY="secret-key")
    request.session = {}
    SessionOrApiKeyAuthentication().authenticate(request)
    key_row.refresh_from_db()
    assert key_row.last_used_at is not None
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest core/tests/test_authentication.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.authentication'`.

- [ ] **Step 3: Write `core/authentication.py`**

```python
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.models import ApiKey, User
from core.security import hash_api_key


class AnonymousServiceUser:
    """Stands in for `request.user` when a valid X-Api-Key header authenticated
    the request instead of a session — mirrors the FastAPI-era
    current_user_or_service dependency returning None for a service caller,
    adapted to DRF's requirement that request.user be truthy."""

    is_authenticated = True
    is_service_account = True
    id = None


class SessionOrApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.META.get("HTTP_X_API_KEY")
        if api_key:
            key_hash = hash_api_key(api_key)
            try:
                key_row = ApiKey.objects.get(key_hash=key_hash)
            except ApiKey.DoesNotExist:
                raise AuthenticationFailed("Invalid API key")
            key_row.last_used_at = timezone.now()
            key_row.save(update_fields=["last_used_at"])
            return (AnonymousServiceUser(), None)

        user_id = request.session.get("user_id")
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return None
            return (user, None)

        return None
```

- [ ] **Step 4: Run to confirm it passes**

```bash
python -m pytest core/tests/test_authentication.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Write `core/permissions.py`**

```python
from rest_framework.permissions import BasePermission


class IsAuthenticatedOrServiceKey(BasePermission):
    """Mirrors the FastAPI-era current_user_or_service dependency: a valid
    session OR a valid X-Api-Key both satisfy this permission. Views on
    mutating routes that must reject service keys (documented per-route in
    Phase 2, same discipline as the old services/*/router.py comments) use a
    stricter permission class instead of this one."""

    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_authenticated", False))
```

- [ ] **Step 6: Add a permission-class test**

```python
# core/tests/test_authentication.py (append)
from core.permissions import IsAuthenticatedOrServiceKey


class _FakeRequest:
    def __init__(self, user):
        self.user = user


def test_permission_denies_anonymous():
    from django.contrib.auth.models import AnonymousUser

    assert IsAuthenticatedOrServiceKey().has_permission(_FakeRequest(AnonymousUser()), None) is False


def test_permission_allows_authenticated_duck_type():
    class _Authed:
        is_authenticated = True

    assert IsAuthenticatedOrServiceKey().has_permission(_FakeRequest(_Authed()), None) is True
```

- [ ] **Step 7: Run all core tests**

```bash
python -m pytest core/ -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add control-panel-django/core/authentication.py control-panel-django/core/permissions.py control-panel-django/core/tests/test_authentication.py
git commit -m "feat: add DRF session-or-api-key authentication and permission class"
```

---

## Task 6: Port the same-origin check middleware

**Files:**
- Create: `control-panel-django/core/middleware.py`
- Test: `control-panel-django/core/tests/test_middleware.py`

**Interfaces:**
- Consumes: `docker` SDK (already in `requirements.txt` from Task 1).
- Produces: `core.middleware.VerifySameOriginMiddleware`, already referenced in `config/settings.py`'s `MIDDLEWARE` list from Task 1.

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_middleware.py
import pytest
from django.test import Client


@pytest.mark.django_db
def test_post_with_mismatched_host_header_is_rejected(settings):
    settings.ALLOWED_HOSTS = ["*"]
    client = Client()
    response = client.post("/admin/login/", HTTP_HOST="evil.example.com")
    assert response.status_code == 403


@pytest.mark.django_db
def test_get_with_mismatched_host_header_is_allowed(settings):
    client = Client()
    response = client.get("/admin/login/", HTTP_HOST="evil.example.com")
    assert response.status_code != 403
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest core/tests/test_middleware.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.middleware'` (via the `MIDDLEWARE` setting failing to import).

- [ ] **Step 3: Write `core/middleware.py`**

```python
import os
import socket

import docker


def _own_network_gateway():
    try:
        client = docker.from_env()
        self_container = client.containers.get(socket.gethostname())
        for net in self_container.attrs.get("NetworkSettings", {}).get("Networks", {}).values():
            if net.get("Gateway"):
                return net["Gateway"]
    except Exception:
        pass
    return None


class VerifySameOriginMiddleware:
    """Ported 1:1 from control-panel/main.py's verify_same_origin (fixed
    under /cso, commit e360961). Defense-in-depth alongside Django's own
    CSRF middleware and session auth — stays in place unchanged through the
    migration per the spec's Auth section."""

    def __init__(self, get_response):
        self.get_response = get_response
        host_ip = os.environ.get("HOST_IP")
        self.allowed_hosts = {h for h in (host_ip, "localhost", "127.0.0.1") if h}
        self.loopback_ips = {"127.0.0.1", "::1"}
        gateway = _own_network_gateway()
        if gateway:
            self.loopback_ips.add(gateway)

    def __call__(self, request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            host = (request.META.get("HTTP_HOST") or "").split(":")[0]
            if host not in self.allowed_hosts:
                from django.http import JsonResponse

                return JsonResponse(
                    {"ok": False, "message": "Rejected: Host header did not match this panel's configured HOST_IP."},
                    status=403,
                )
            if host in ("localhost", "127.0.0.1"):
                client_host = request.META.get("REMOTE_ADDR")
                if client_host not in self.loopback_ips:
                    from django.http import JsonResponse

                    return JsonResponse(
                        {"ok": False, "message": "Rejected: Host header claimed localhost but the connection wasn't actually local."},
                        status=403,
                    )
            origin = request.META.get("HTTP_ORIGIN")
            if origin:
                origin_host = origin.split("://", 1)[-1].split(":")[0].split("/")[0]
                if origin_host not in self.allowed_hosts:
                    from django.http import JsonResponse

                    return JsonResponse(
                        {"ok": False, "message": "Rejected: Origin did not match this panel's host."},
                        status=403,
                    )
        return self.get_response(request)
```

- [ ] **Step 4: Run to confirm the tests pass**

```bash
python -m pytest core/tests/test_middleware.py -v
```

Expected: `2 passed`. (`HOST_IP` unset in the test environment means `allowed_hosts = {"localhost", "127.0.0.1"}`; `evil.example.com` is rejected on POST, allowed on GET.)

- [ ] **Step 5: Commit**

```bash
git add control-panel-django/core/middleware.py control-panel-django/core/tests/test_middleware.py
git commit -m "feat: port same-origin verification middleware"
```

---

## Task 7: `auth_app` — login/logout views

**Files:**
- Create: `control-panel-django/auth_app/__init__.py`
- Create: `control-panel-django/auth_app/apps.py`
- Create: `control-panel-django/auth_app/views.py`
- Create: `control-panel-django/auth_app/urls.py`
- Create: `control-panel-django/auth_app/templates/auth_app/login.html`
- Test: `control-panel-django/auth_app/tests/__init__.py`
- Test: `control-panel-django/auth_app/tests/test_views.py`

**Interfaces:**
- Consumes: `core.models.User`, `core.security.verify_password`.
- Produces: `auth_app:login` and `auth_app:logout` URL names (referenced by `LOGIN_URL` in Task 1's settings, and by every later template's nav bar); sets/clears `request.session["user_id"]`, the same session key `core.authentication.SessionOrApiKeyAuthentication` reads.

- [ ] **Step 1: Write the failing test**

```python
# auth_app/tests/test_views.py
import pytest
from django.test import Client
from django.urls import reverse

from core.models import User


@pytest.mark.django_db
def test_login_with_correct_credentials_sets_session():
    user = User(username="bear")
    user.set_password("hunter2")
    user.save()

    client = Client()
    response = client.post(reverse("auth_app:login"), {"username": "bear", "password": "hunter2"})

    assert response.status_code == 302
    assert client.session["user_id"] == user.id


@pytest.mark.django_db
def test_login_with_wrong_password_shows_error():
    user = User(username="bear")
    user.set_password("hunter2")
    user.save()

    client = Client()
    response = client.post(reverse("auth_app:login"), {"username": "bear", "password": "wrong"})

    assert response.status_code == 200
    assert "user_id" not in client.session
    assert b"Invalid username or password" in response.content


@pytest.mark.django_db
def test_login_with_unknown_username_shows_error():
    client = Client()
    response = client.post(reverse("auth_app:login"), {"username": "ghost", "password": "x"})

    assert response.status_code == 200
    assert b"Invalid username or password" in response.content


@pytest.mark.django_db
def test_logout_clears_session():
    user = User(username="bear")
    user.set_password("hunter2")
    user.save()

    client = Client()
    client.post(reverse("auth_app:login"), {"username": "bear", "password": "hunter2"})
    assert client.session["user_id"] == user.id

    response = client.post(reverse("auth_app:logout"))
    assert response.status_code == 302
    assert "user_id" not in client.session


@pytest.mark.django_db
def test_login_page_renders():
    client = Client()
    response = client.get(reverse("auth_app:login"))
    assert response.status_code == 200
    assert b"<form" in response.content
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest auth_app/tests/test_views.py -v
```

Expected: `django.urls.exceptions.NoReverseMatch` — `auth_app` isn't installed/routed yet.

- [ ] **Step 3: Write `auth_app/apps.py`**

```python
from django.apps import AppConfig


class AuthAppConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "auth_app"
```

- [ ] **Step 4: Write `auth_app/views.py`**

```python
from django.shortcuts import redirect, render

from core.models import User


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return render(request, "auth_app/login.html", {"error": "Invalid username or password"})

        if not user.check_password(password):
            return render(request, "auth_app/login.html", {"error": "Invalid username or password"})

        request.session["user_id"] = user.id
        return redirect("/")

    return render(request, "auth_app/login.html")


def logout_view(request):
    request.session.pop("user_id", None)
    return redirect("auth_app:login")
```

- [ ] **Step 5: Write `auth_app/urls.py`**

```python
from django.urls import path

from auth_app import views

app_name = "auth_app"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
```

- [ ] **Step 6: Write `auth_app/templates/auth_app/login.html`**

```html
<!doctype html>
<html>
<head><title>control-panel — log in</title></head>
<body>
  <h1>control-panel</h1>
  {% if error %}<p style="color:red">{{ error }}</p>{% endif %}
  <form method="post">
    {% csrf_token %}
    <label>Username <input type="text" name="username" autofocus></label>
    <label>Password <input type="password" name="password"></label>
    <button type="submit">Log in</button>
  </form>
</body>
</html>
```

- [ ] **Step 7: Wire `config/urls.py` and `config/settings.py`**

```python
# config/settings.py — INSTALLED_APPS already lists "auth_app" from Task 1, no change needed here.
```

```python
# config/urls.py — replace the file
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("auth_app.urls")),
]
```

- [ ] **Step 8: Run the tests to confirm they pass**

```bash
python -m pytest auth_app/ -v
```

Expected: `5 passed`.

- [ ] **Step 9: Commit**

```bash
git add control-panel-django/auth_app/ control-panel-django/config/urls.py
git commit -m "feat: add auth_app login/logout views backed by core.models.User sessions"
```

---

## Task 8: Bootstrap management command

**Files:**
- Create: `control-panel-django/core/management/__init__.py`
- Create: `control-panel-django/core/management/commands/__init__.py`
- Create: `control-panel-django/core/management/commands/bootstrap.py`
- Test: `control-panel-django/core/tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `core.models.User`, `core.models.ApiKey`, `core.security.hash_password`, `core.security.hash_api_key`.
- Produces: `python manage.py bootstrap` — idempotent, run once at container start in Phase 5 (mirrors `main.py`'s `_bootstrap_admin`/`_bootstrap_service_key`, called from `_startup()`).

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_bootstrap.py
import pytest
from django.core.management import call_command

from core.models import ApiKey, User
from core.security import hash_api_key


@pytest.mark.django_db
def test_bootstrap_creates_admin_user_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("CONTROL_PANEL_ADMIN_USERNAME", "bear")
    monkeypatch.setenv("CONTROL_PANEL_ADMIN_PASSWORD", "hunter2")

    call_command("bootstrap")

    user = User.objects.get(username="bear")
    assert user.is_admin is True
    assert user.check_password("hunter2") is True


@pytest.mark.django_db
def test_bootstrap_is_a_noop_if_a_user_already_exists(monkeypatch):
    User.objects.create(username="existing", password_hash="x")
    monkeypatch.setenv("CONTROL_PANEL_ADMIN_USERNAME", "bear")
    monkeypatch.setenv("CONTROL_PANEL_ADMIN_PASSWORD", "hunter2")

    call_command("bootstrap")

    assert User.objects.count() == 1
    assert not User.objects.filter(username="bear").exists()


@pytest.mark.django_db
def test_bootstrap_skips_admin_creation_without_env_vars(monkeypatch):
    monkeypatch.delenv("CONTROL_PANEL_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("CONTROL_PANEL_ADMIN_PASSWORD", raising=False)

    call_command("bootstrap")

    assert User.objects.count() == 0


@pytest.mark.django_db
def test_bootstrap_upserts_service_api_key(monkeypatch):
    monkeypatch.setenv("CONTROL_PANEL_SERVICE_API_KEY", "secret-key")

    call_command("bootstrap")
    call_command("bootstrap")  # idempotent — re-running must not create a duplicate row

    assert ApiKey.objects.filter(name="healthcheck-cron").count() == 1
    assert ApiKey.objects.get(name="healthcheck-cron").key_hash == hash_api_key("secret-key")
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest core/tests/test_bootstrap.py -v
```

Expected: `django.core.management.base.CommandError: Unknown command: 'bootstrap'`.

- [ ] **Step 3: Write `core/management/commands/bootstrap.py`**

```python
import os

from django.core.management.base import BaseCommand

from core.models import ApiKey, User
from core.security import hash_api_key, hash_password


class Command(BaseCommand):
    help = "Idempotently creates the single admin account and upserts the service API key from env vars."

    def handle(self, *args, **options):
        self._bootstrap_admin()
        self._bootstrap_service_key()

    def _bootstrap_admin(self):
        username = os.environ.get("CONTROL_PANEL_ADMIN_USERNAME")
        password = os.environ.get("CONTROL_PANEL_ADMIN_PASSWORD")
        if not username or not password:
            return
        if User.objects.exists():
            return
        user = User(username=username, is_admin=True)
        user.password_hash = hash_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Created admin user '{username}'"))

    def _bootstrap_service_key(self):
        raw_key = os.environ.get("CONTROL_PANEL_SERVICE_API_KEY")
        if not raw_key:
            return
        key_hash = hash_api_key(raw_key)
        existing = ApiKey.objects.filter(name="healthcheck-cron").first()
        if existing is not None:
            existing.key_hash = key_hash
            existing.save(update_fields=["key_hash"])
        else:
            ApiKey.objects.create(name="healthcheck-cron", key_hash=key_hash)
        self.stdout.write(self.style.SUCCESS("Upserted healthcheck-cron service API key"))
```

- [ ] **Step 4: Run to confirm it passes**

```bash
python -m pytest core/tests/test_bootstrap.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add control-panel-django/core/management/
git commit -m "feat: add bootstrap management command for admin user and service api key"
```

---

## Task 9: `/healthz` view, full-suite run, coverage gate

**Files:**
- Modify: `control-panel-django/config/urls.py`
- Create: `control-panel-django/core/views.py`
- Test: `control-panel-django/core/tests/test_views.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `GET /healthz` returning `{"status": "ok"}` — same contract as `control-panel/main.py`'s `@app.get("/healthz")`, so Phase 5's docker-compose healthcheck config needs no changes.

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_views.py
import json

import pytest
from django.test import Client


@pytest.mark.django_db
def test_healthz_returns_ok():
    client = Client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest core/tests/test_views.py -v
```

Expected: `404` — no `/healthz` route exists.

- [ ] **Step 3: Write `core/views.py`**

```python
from django.http import JsonResponse


def healthz(request):
    return JsonResponse({"status": "ok"})
```

- [ ] **Step 4: Wire it into `config/urls.py`**

```python
# config/urls.py — replace the file
from django.contrib import admin
from django.urls import include, path

from core.views import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("auth_app.urls")),
    path("healthz", healthz),
]
```

- [ ] **Step 5: Run to confirm it passes**

```bash
python -m pytest core/tests/test_views.py -v
```

Expected: `1 passed`.

- [ ] **Step 6: Run the full Phase 1 test suite with coverage**

```bash
cd control-panel-django
python -m pytest --cov=core --cov=auth_app --cov-report=term-missing
```

Expected: all tests pass; coverage ≥80% on both `core` and `auth_app`. If any module falls short, add the missing-branch test (e.g. an `AuthenticationFailed` path, an `AppConfig` import) before proceeding — do not lower the gate.

- [ ] **Step 7: `manage.py check` one more time end-to-end**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 8: Commit**

```bash
git add control-panel-django/core/views.py control-panel-django/config/urls.py
git commit -m "feat: add /healthz endpoint, close out Phase 1 with full test suite green"
```

---

## Self-Review Notes

- **Spec coverage:** Goal 4 (data preservation) → Task 3. Goal 5 (80%+ coverage) → Task 9. Auth section (session + service-key) → Tasks 5–7. "Django admin for models" decision → Task 2 Step 5. Deployment/env-var reuse constraint → honored throughout (Task 1 settings, Task 8 command) with zero new env var names introduced.
- **Deferred to later phases, intentionally not in this plan:** `services.py` client ports (`arr_client`, `plex_client`, etc.), `/api/v2/*` per-app endpoints, template UI beyond the login page, gunicorn/Dockerfile changes, fish CLI updates, and the actual `migrate --fake-initial` run against production `/data/control-panel.db` (Task 3 only rehearses it against a throwaway copy). These are Phases 2–5 per the spec's "Open Risks" section and get their own plan documents once this phase is reviewed.
- **Naming discrepancy from the spec:** the spec's Current State section says "10 models"; the actual `control-panel/models/__init__.py` registers 9. This plan ports the 9 that actually exist — no phantom 10th model.
