from django.urls import path

from cleanuparr.api.views import InstancesView, StrikesView

app_name = "cleanuparr_api"

urlpatterns = [
    path("instances", InstancesView.as_view(), name="instances"),
    path("strikes", StrikesView.as_view(), name="strikes"),
]
