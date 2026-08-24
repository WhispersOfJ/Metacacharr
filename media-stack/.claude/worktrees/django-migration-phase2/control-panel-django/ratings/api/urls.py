from django.urls import path

from ratings.api.views import ImdbRatingView, MdblistRatingView

app_name = "ratings_api"

urlpatterns = [
    path("imdb", ImdbRatingView.as_view(), name="imdb"),
    path("mdblist", MdblistRatingView.as_view(), name="mdblist"),
]
