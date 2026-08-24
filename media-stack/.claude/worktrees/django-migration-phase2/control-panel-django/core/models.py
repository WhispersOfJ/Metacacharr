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

    def check_password(self, raw_password: str) -> bool:
        from core.security import verify_password

        return verify_password(raw_password, self.password_hash)

    def set_password(self, raw_password: str) -> None:
        from core.security import hash_password

        self.password_hash = hash_password(raw_password)

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
