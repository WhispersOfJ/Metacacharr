using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;

namespace Metacache.Host.Tests;

/// <summary>
/// Canned TMDB v3 responses and a path-based router for <see cref="FakeUpstream"/>,
/// shared by the TMDB client unit tests and the match/metadata endpoint tests.
/// Base URL is https://api.themoviedb.org/3, so absolute paths start with "/3/…".
/// </summary>
public static class TmdbTestData
{
    public const string BaseUrl = "https://api.themoviedb.org/3";

    public const string Movie105Json = """
        {
          "adult": false,
          "backdrop_path": "/bttf-backdrop.jpg",
          "budget": 19000000,
          "genres": [ { "id": 12, "name": "Adventure" }, { "id": 35, "name": "Comedy" } ],
          "id": 105,
          "imdb_id": "tt0088763",
          "original_language": "en",
          "original_title": "Back to the Future",
          "overview": "Marty McFly travels back in time.",
          "popularity": 55.5,
          "poster_path": "/bttf-poster.jpg",
          "production_companies": [ { "id": 33, "name": "Universal Pictures" } ],
          "production_countries": [ { "iso_3166_1": "US", "name": "United States of America" } ],
          "release_date": "1985-07-03",
          "revenue": 381000000,
          "runtime": 116,
          "spoken_languages": [ { "iso_639_1": "en", "name": "English" } ],
          "status": "Released",
          "tagline": "He was never in time for his classes...",
          "title": "Back to the Future",
          "video": false,
          "vote_average": 8.3,
          "vote_count": 19000
        }
        """;

    public const string Movie165Json = """
        {
          "adult": false,
          "backdrop_path": "/bttf2-backdrop.jpg",
          "budget": 40000000,
          "genres": [ { "id": 12, "name": "Adventure" }, { "id": 35, "name": "Comedy" } ],
          "id": 165,
          "imdb_id": "tt0096874",
          "original_language": "en",
          "original_title": "Back to the Future Part II",
          "overview": "Marty travels to 2015.",
          "popularity": 40.1,
          "poster_path": "/bttf2-poster.jpg",
          "production_companies": [ { "id": 33, "name": "Universal Pictures" } ],
          "production_countries": [ { "iso_3166_1": "US", "name": "United States of America" } ],
          "release_date": "1989-11-22",
          "revenue": 332000000,
          "runtime": 108,
          "spoken_languages": [ { "iso_639_1": "en", "name": "English" } ],
          "status": "Released",
          "tagline": "Roads? Where we're going, we don't need roads.",
          "title": "Back to the Future Part II",
          "video": false,
          "vote_average": 7.8,
          "vote_count": 12000
        }
        """;

    public const string Movie999Json = """
        {
          "adult": true,
          "backdrop_path": null,
          "genres": [],
          "id": 999,
          "imdb_id": null,
          "original_language": "xx",
          "original_title": "Explicit",
          "overview": "",
          "popularity": 70.0,
          "poster_path": "/explicit-poster.jpg",
          "production_companies": [],
          "production_countries": [],
          "release_date": "2020-01-01",
          "runtime": 90,
          "tagline": "",
          "title": "Explicit",
          "video": false,
          "vote_average": 4.1,
          "vote_count": 10
        }
        """;

    public const string SearchJson = """
        {
          "page": 1,
          "results": [
            {
              "adult": false,
              "backdrop_path": "/bttf-backdrop.jpg",
              "id": 105,
              "original_language": "en",
              "original_title": "Back to the Future",
              "overview": "Marty McFly travels back in time.",
              "popularity": 55.5,
              "poster_path": "/bttf-poster.jpg",
              "release_date": "1985-07-03",
              "title": "Back to the Future",
              "video": false,
              "vote_average": 8.3,
              "vote_count": 19000
            },
            {
              "adult": false,
              "backdrop_path": "/bttf2-backdrop.jpg",
              "id": 165,
              "original_language": "en",
              "original_title": "Back to the Future Part II",
              "overview": "Marty travels to 2015.",
              "popularity": 40.1,
              "poster_path": "/bttf2-poster.jpg",
              "release_date": "1989-11-22",
              "title": "Back to the Future Part II",
              "video": false,
              "vote_average": 7.8,
              "vote_count": 12000
            }
          ]
        }
        """;

    /// <summary>Only an adult movie — used to verify includeAdult filtering.</summary>
    public const string AdultSearchJson = """
        {
          "page": 1,
          "results": [
            {
              "adult": true,
              "backdrop_path": null,
              "id": 999,
              "original_language": "xx",
              "original_title": "Explicit",
              "overview": "",
              "popularity": 70.0,
              "poster_path": "/explicit-poster.jpg",
              "release_date": "2020-01-01",
              "title": "Explicit",
              "video": false,
              "vote_average": 4.1,
              "vote_count": 10
            }
          ]
        }
        """;

    public const string Find105Json = """
        {
          "movie_results": [
            {
              "adult": false,
              "backdrop_path": "/bttf-backdrop.jpg",
              "id": 105,
              "original_language": "en",
              "original_title": "Back to the Future",
              "overview": "Marty McFly travels back in time.",
              "popularity": 55.5,
              "poster_path": "/bttf-poster.jpg",
              "release_date": "1985-07-03",
              "title": "Back to the Future",
              "video": false,
              "vote_average": 8.3,
              "vote_count": 19000
            }
          ]
        }
        """;

    public const string EmptyFindJson = """{ "movie_results": [] }""";

    // ---- movie credits / release dates ----

    public const string MovieCreditsJson = """
        {
          "id": 105,
          "cast": [
            { "id": 4, "name": "Michael J. Fox", "character": "Marty McFly", "order": 0, "profile_path": "/fox.jpg" },
            { "id": 5, "name": "Christopher Lloyd", "character": "Emmett Brown", "order": 1, "profile_path": "/lloyd.jpg" }
          ],
          "crew": [
            { "id": 1, "name": "Robert Zemeckis", "job": "Director", "department": "Directing", "order": 0, "profile_path": "/zemeckis.jpg" },
            { "id": 2, "name": "Bob Gale", "job": "Writer", "department": "Writing", "order": 1, "profile_path": "/gale.jpg" },
            { "id": 3, "name": "Neil Canton", "job": "Producer", "department": "Production", "order": 2, "profile_path": null }
          ]
        }
        """;

    public const string ReleaseDatesJson = """
        {
          "results": [
            { "iso_3166_1": "US", "release_dates": [ { "certification": "PG", "type": 3 } ] },
            { "iso_3166_1": "DE", "release_dates": [ { "certification": "FSK 12", "type": 3 } ] }
          ]
        }
        """;

    // ---- TV ----

    public const int ShowId = 15260;

    public const string TvSearchJson = """
        {
          "page": 1,
          "results": [
            {
              "adult": false,
              "backdrop_path": "/at-backdrop.jpg",
              "first_air_date": "2010-04-05",
              "id": 15260,
              "name": "Adventure Time",
              "original_language": "en",
              "original_name": "Adventure Time",
              "overview": "Unlikely heroes Finn and Jake.",
              "popularity": 80.0,
              "poster_path": "/at-poster.jpg",
              "vote_average": 8.5,
              "vote_count": 3000
            }
          ]
        }
        """;

    public const string TvShowJson = """
        {
          "adult": false,
          "backdrop_path": "/at-backdrop.jpg",
          "episode_run_time": [ 11 ],
          "first_air_date": "2010-04-05",
          "genres": [ { "id": 16, "name": "Animation" } ],
          "id": 15260,
          "last_air_date": "2018-09-03",
          "name": "Adventure Time",
          "networks": [ { "id": 56, "name": "Cartoon Network" } ],
          "original_language": "en",
          "original_name": "Adventure Time",
          "overview": "Unlikely heroes Finn and Jake.",
          "popularity": 80.0,
          "poster_path": "/at-poster.jpg",
          "production_companies": [ { "id": 7846, "name": "Cartoon Network Studios" } ],
          "production_countries": [ { "iso_3166_1": "US", "name": "United States of America" } ],
          "seasons": [
            { "air_date": "2010-04-05", "episode_count": 26, "id": 3624, "name": "Season 1", "overview": "", "poster_path": "/at-s1.jpg", "season_number": 1 },
            { "air_date": "2010-10-11", "episode_count": 26, "id": 3625, "name": "Season 2", "overview": "", "poster_path": "/at-s2.jpg", "season_number": 2 }
          ],
          "vote_average": 8.5,
          "vote_count": 3000
        }
        """;

    public const string Season1Json = """
        {
          "air_date": "2010-04-05",
          "episodes": [
            { "air_date": "2010-04-05", "episode_number": 1, "id": 71833, "name": "Slumber Party Panic", "overview": "Finn and Jake fight zombies.", "runtime": 11, "season_number": 1, "still_path": "/at-e1.jpg", "vote_average": 7.8 },
            { "air_date": "2010-04-05", "episode_number": 2, "id": 71834, "name": "Trouble in Lumpy Space", "overview": "Lumpy Space Princess visits.", "runtime": 11, "season_number": 1, "still_path": "/at-e2.jpg", "vote_average": 7.6 }
          ],
          "id": 3624,
          "name": "Season 1",
          "overview": "The first season of Adventure Time.",
          "poster_path": "/at-s1.jpg",
          "season_number": 1
        }
        """;

    public const string Season2Json = """
        {
          "air_date": "2010-10-11",
          "episodes": [
            { "air_date": "2010-10-11", "episode_number": 1, "id": 71840, "name": "It Came from the Nightosphere", "overview": "Marceline's dad shows up.", "runtime": 11, "season_number": 2, "still_path": "/at-e3.jpg", "vote_average": 8.1 }
          ],
          "id": 3625,
          "name": "Season 2",
          "overview": "The second season of Adventure Time.",
          "poster_path": "/at-s2.jpg",
          "season_number": 2
        }
        """;

    public const string Episode11Json = """
        {
          "air_date": "2010-04-05",
          "episode_number": 1,
          "id": 71833,
          "name": "Slumber Party Panic",
          "overview": "Finn and Jake fight zombies.",
          "runtime": 11,
          "season_number": 1,
          "still_path": "/at-e1.jpg",
          "vote_average": 7.8
        }
        """;

    public const string ShowCreditsJson = """
        {
          "id": 15260,
          "cast": [
            { "id": 100, "name": "Jeremy Shada", "character": "Finn (voice)", "order": 0, "profile_path": "/shada.jpg" }
          ],
          "crew": [
            { "id": 101, "name": "Pendleton Ward", "job": "Creator", "department": "Writing", "order": 0, "profile_path": "/ward.jpg" }
          ]
        }
        """;

    public const string ShowContentRatingsJson = """
        {
          "results": [
            { "iso_3166_1": "US", "rating": "TV-PG" },
            { "iso_3166_1": "DE", "rating": "FSK 6" }
          ]
        }
        """;

    public const string ShowExternalIdsJson = """
        { "id": 15260, "imdb_id": "tt1305826", "tvdb_id": 152831 }
        """;

    public const string FindTvJson = """
        {
          "movie_results": [],
          "tv_results": [
            {
              "adult": false,
              "backdrop_path": "/at-backdrop.jpg",
              "first_air_date": "2010-04-05",
              "id": 15260,
              "name": "Adventure Time",
              "original_language": "en",
              "original_name": "Adventure Time",
              "overview": "Unlikely heroes Finn and Jake.",
              "popularity": 80.0,
              "poster_path": "/at-poster.jpg",
              "vote_average": 8.5
            }
          ]
        }
        """;

    // ---- ARR (M3 warming) ----

    public const string RadarrMoviesJson = """
        [
          { "id": 1, "title": "Back to the Future", "tmdbId": 105, "year": 1985 },
          { "id": 2, "title": "Back to the Future Part II", "tmdbId": 165, "year": 1989 }
        ]
        """;

    public const string SonarrSeriesJson = """
        [
          { "id": 1, "title": "Adventure Time", "tvdbId": 152831, "year": 2010 }
        ]
        """;

    /// <summary>
    /// Routes the canned responses by path; throws on anything unexpected. When
    /// arrMovies/arrSeries are supplied, /api/v3/movie and /api/v3/series are served
    /// for the M3 warmer tests.
    /// </summary>
    public static void Route(this FakeUpstream upstream, string baseUrl = BaseUrl, string? arrMovies = null, string? arrSeries = null)
    {
        upstream.Handler = request =>
        {
            string path = request.Url.AbsolutePath;
            if (arrMovies is not null && path.EndsWith("/api/v3/movie", StringComparison.Ordinal))
                return Json(arrMovies);
            if (arrSeries is not null && path.EndsWith("/api/v3/series", StringComparison.Ordinal))
                return Json(arrSeries);
            if (path.EndsWith("/search/movie", StringComparison.Ordinal))
                return Json(request.Url.Query.Contains("query=Explicit", StringComparison.Ordinal) ? AdultSearchJson : SearchJson);
            if (path.EndsWith("/search/tv", StringComparison.Ordinal))
                return Json(TvSearchJson);
            if (path.EndsWith("/movie/105/credits", StringComparison.Ordinal))
                return Json(MovieCreditsJson);
            if (path.EndsWith("/movie/105/release_dates", StringComparison.Ordinal))
                return Json(ReleaseDatesJson);
            if (path.EndsWith("/tv/15260/credits", StringComparison.Ordinal))
                return Json(ShowCreditsJson);
            if (path.EndsWith("/tv/15260/content_ratings", StringComparison.Ordinal))
                return Json(ShowContentRatingsJson);
            if (path.EndsWith("/tv/15260/external_ids", StringComparison.Ordinal))
                return Json(ShowExternalIdsJson);
            if (path.EndsWith("/tv/15260/season/1/episode/1", StringComparison.Ordinal))
                return Json(Episode11Json);
            if (path.EndsWith("/tv/15260/season/1", StringComparison.Ordinal))
                return Json(Season1Json);
            if (path.EndsWith("/tv/15260/season/2", StringComparison.Ordinal))
                return Json(Season2Json);
            if (path.Contains("/tv/15260/season/", StringComparison.Ordinal))
                return JsonStatus(404, """{ "status_code": 34 }""");
            if (path.EndsWith("/tv/15260", StringComparison.Ordinal))
                return Json(TvShowJson);
            if (path.EndsWith("/tv/999999999", StringComparison.Ordinal))
                return JsonStatus(404, """{ "status_code": 34 }""");
            if (path.EndsWith("/movie/999999999", StringComparison.Ordinal))
                return JsonStatus(404, """{ "status_code": 34, "status_message": "The resource you requested could not be found." }""");
            if (path.EndsWith("/movie/165/credits", StringComparison.Ordinal))
                return Json(MovieCreditsJson);
            if (path.EndsWith("/movie/165/release_dates", StringComparison.Ordinal))
                return Json(ReleaseDatesJson);
            if (path.EndsWith("/movie/165", StringComparison.Ordinal))
                return Json(Movie165Json);
            if (path.EndsWith("/movie/999", StringComparison.Ordinal))
                return Json(Movie999Json);
            if (path.Contains("/movie/105", StringComparison.Ordinal))
                return Json(Movie105Json);
            if (path.EndsWith("/find/tt0088763", StringComparison.Ordinal))
                return Json(Find105Json);
            if (path.EndsWith("/find/tt1305826", StringComparison.Ordinal))
                return Json(FindTvJson);
            if (path.EndsWith("/find/152831", StringComparison.Ordinal))
                return Json(FindTvJson);
            if (path.EndsWith("/find/tt999999", StringComparison.Ordinal))
                return Json(EmptyFindJson);
            if (path.StartsWith("/t/p/", StringComparison.Ordinal))
                return new UpstreamResponse(200, TestBytes.Of("fake-jpeg-bytes"), "image/jpeg", null, null, null);
            throw new InvalidOperationException($"Unexpected upstream request: {request.Url}");
        };

        static UpstreamResponse Json(string body) => new(200, TestBytes.Of(body), "application/json", null, null, null);
        static UpstreamResponse JsonStatus(int status, string body) => new(status, TestBytes.Of(body), "application/json", null, null, null);
    }
}
