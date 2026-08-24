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
