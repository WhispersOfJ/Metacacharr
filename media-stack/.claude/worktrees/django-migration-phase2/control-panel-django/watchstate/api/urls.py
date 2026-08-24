from django.urls import path

from watchstate.api.views import HistoryView, ImportView, StatusView

app_name = "watchstate_api"

urlpatterns = [
    path("status", StatusView.as_view(), name="status"),
    path("import", ImportView.as_view(), name="import"),
    path("history", HistoryView.as_view(), name="history"),
]
