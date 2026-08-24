from core.api_base import EnvelopeAPIView
from ratings import services
from ratings.api.serializers import RatingQuerySerializer


class ImdbRatingView(EnvelopeAPIView):
    def get(self, request):
        query = RatingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.get_imdb_rating(query.validated_data["imdb_id"])
        return self.ok("IMDb rating fetched", **result)


class MdblistRatingView(EnvelopeAPIView):
    def get(self, request):
        query = RatingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.get_mdblist_rating(query.validated_data["imdb_id"])
        return self.ok("MDBList rating fetched", **result)
