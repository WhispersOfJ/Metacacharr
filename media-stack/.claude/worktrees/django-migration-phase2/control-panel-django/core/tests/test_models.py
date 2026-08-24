import pytest

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


@pytest.mark.django_db
def test_user_table_name_matches_existing_schema():
    assert User._meta.db_table == "users"


@pytest.mark.django_db
def test_user_defaults():
    user = User.objects.create(username="bear", password_hash="argon2-hash-placeholder")
    assert user.is_admin is True
    assert user.created_at is not None


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


@pytest.mark.django_db
def test_user_set_password_and_check_password():
    user = User(username="bear")
    user.set_password("hunter2")
    user.save()
    assert user.check_password("hunter2") is True
    assert user.check_password("wrong") is False
