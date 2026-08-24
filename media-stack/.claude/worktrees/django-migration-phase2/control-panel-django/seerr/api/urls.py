from django.urls import path

from seerr.api.views import SeerrRequestsView

app_name = "seerr_api"

urlpatterns = [
    path("requests", SeerrRequestsView.as_view(), name="requests"),
]
