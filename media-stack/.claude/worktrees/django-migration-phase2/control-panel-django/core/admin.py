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
