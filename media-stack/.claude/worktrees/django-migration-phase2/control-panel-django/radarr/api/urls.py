from django.urls import path

from radarr.api.views import ExcludeMovieView

app_name = "radarr_api"

urlpatterns = [
    path("exclude", ExcludeMovieView.as_view(), name="exclude"),
]
