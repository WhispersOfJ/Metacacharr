from django.urls import path

from queue_app.api.views import QueueStatusView

app_name = "queue_api"

urlpatterns = [
    path("status", QueueStatusView.as_view(), name="status"),
]
