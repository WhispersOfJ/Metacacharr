from django.urls import path

from prowlarr.api.views import ProwlarrIndexersView

app_name = "prowlarr_api"

urlpatterns = [
    path("indexers", ProwlarrIndexersView.as_view(), name="indexers"),
]
