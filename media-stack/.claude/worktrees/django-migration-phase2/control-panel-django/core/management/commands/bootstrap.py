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
