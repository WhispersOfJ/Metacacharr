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

    /// <summary>Routes the canned responses by path; throws on anything unexpected.</summary>
    public static void Route(this FakeUpstream upstream, string baseUrl = BaseUrl)
    {
        upstream.Handler = request =>
        {
            string path = request.Url.AbsolutePath;
            if (path.EndsWith("/search/movie", StringComparison.Ordinal))
                return Json(request.Url.Query.Contains("query=Explicit", StringComparison.Ordinal) ? AdultSearchJson : SearchJson);
            if (path.EndsWith("/movie/999999999", StringComparison.Ordinal))
                return JsonStatus(404, """{ "status_code": 34, "status_message": "The resource you requested could not be found." }""");
            if (path.EndsWith("/movie/165", StringComparison.Ordinal))
                return Json(Movie165Json);
            if (path.EndsWith("/movie/999", StringComparison.Ordinal))
                return Json(Movie999Json);
            if (path.Contains("/movie/105", StringComparison.Ordinal))
                return Json(Movie105Json);
            if (path.EndsWith("/find/tt0088763", StringComparison.Ordinal))
                return Json(Find105Json);
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
