using System.Net;
using Metacache.Core.Cache;
using Metacache.Core.Providers;
using Metacache.Host.Tests.Cache;
using Microsoft.Extensions.Logging.Abstractions;

namespace Metacache.Host.Tests.Providers;

public class TmdbClientTests
{
    private sealed class Fixture : IDisposable
    {
        public FakeClock Clock { get; } = new(DateTimeOffset.Parse("2026-08-24T00:00:00+00:00"));
        public FakeUpstream Upstream { get; } = new();
        public CacheStore Store { get; }
        public TmdbClient Client { get; }

        public Fixture(string apiKey = "test-api-key", TmdbAuthMode auth = TmdbAuthMode.Bearer)
        {
            Store = new CacheStore(":memory:", Clock);
            var cache = new UpstreamCache(Store, Upstream, new SingleFlight(), Clock, NullLogger<UpstreamCache>.Instance);
            Client = new TmdbClient(
                new TmdbOptions(ApiKey: apiKey, BaseUrl: TmdbTestData.BaseUrl, Auth: auth),
                cache, NullLogger<TmdbClient>.Instance);
        }

        public void Dispose() => Store.Dispose();
    }

    [Fact]
    public async Task Search_builds_normalized_url_and_sends_bearer_auth()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.SearchJson);

        await f.Client.SearchMoviesAsync("Back to the Future", 1985, "en-US", includeAdult: false);

        UpstreamRequest request = Assert.Single(f.Upstream.Requests);
        Assert.Equal("Bearer test-api-key", request.Headers!["Authorization"]);
        Assert.False(request.Url.Query.Contains("api_key", StringComparison.OrdinalIgnoreCase),
            "the API key must not appear in the URL");

        string url = request.Url.AbsoluteUri; // ToString() would unescape %20
        Assert.StartsWith($"{TmdbTestData.BaseUrl}/search/movie?", url);
        Assert.Contains("query=Back%20to%20the%20Future", url);
        Assert.Contains("year=1985", url);
        Assert.Contains("language=en-US", url);
        Assert.Contains("include_adult=false", url);
        // Query params sorted: include_adult < language < page < query < year
        int includeAdult = url.IndexOf("include_adult=", StringComparison.Ordinal);
        int language = url.IndexOf("language=", StringComparison.Ordinal);
        int query = url.IndexOf("query=", StringComparison.Ordinal);
        int year = url.IndexOf("year=", StringComparison.Ordinal);
        Assert.True(includeAdult < language && language < query && query < year);
    }

    [Fact]
    public async Task Search_parses_results_into_summaries()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.SearchJson);

        IReadOnlyList<TmdbMovieSummary> results = await f.Client.SearchMoviesAsync("Back to the Future", null, "en-US", includeAdult: false);

        Assert.Equal(2, results.Count);
        TmdbMovieSummary first = results[0];
        Assert.Equal(105, first.Id);
        Assert.Equal("Back to the Future", first.Title);
        Assert.Equal("1985-07-03", first.ReleaseDate);
        Assert.Equal("en", first.OriginalLanguage);
        Assert.Equal(55.5, first.Popularity);
        Assert.False(first.Adult);
    }

    [Fact]
    public async Task Search_is_cached_until_ttl()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.SearchJson);

        await f.Client.SearchMoviesAsync("Back to the Future", null, "en-US", includeAdult: false);
        await f.Client.SearchMoviesAsync("Back to the Future", null, "en-US", includeAdult: false);

        Assert.Single(f.Upstream.Requests);
    }

    [Fact]
    public async Task GetMovie_parses_details()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.Movie105Json);

        TmdbMovie movie = await f.Client.GetMovieAsync(105, "en-US");

        Assert.Equal(105, movie.Id);
        Assert.Equal("tt0088763", movie.ImdbId);
        Assert.Equal(116, movie.Runtime);
        Assert.Equal(8.3, movie.VoteAverage);
        Assert.Equal(["Adventure", "Comedy"], movie.Genres!.Select(g => g.Name));
        Assert.Equal("Universal Pictures", movie.ProductionCompanies![0].Name);
        Assert.Equal("United States of America", movie.ProductionCountries![0].Name);
    }

    [Fact]
    public async Task GetMovie_404_throws_not_found()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(404, [], null, null, null, null);

        await Assert.ThrowsAsync<TmdbNotFoundException>(() => f.Client.GetMovieAsync(999999999, "en-US"));
    }

    [Fact]
    public async Task Different_languages_use_separate_cache_keys()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.Movie105Json);

        await f.Client.GetMovieAsync(105, "en-US");
        await f.Client.GetMovieAsync(105, "de-DE");

        Assert.Equal(2, f.Upstream.Requests.Count);
    }

    [Fact]
    public async Task FindByExternalId_uses_the_external_source()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.Find105Json);

        IReadOnlyList<TmdbMovieSummary> results = await f.Client.FindByExternalIdAsync("imdb_id", "tt0088763", "en-US");

        Assert.Single(results);
        Assert.Equal(105, results[0].Id);
        Assert.Contains("external_source=imdb_id", f.Upstream.Requests.Single().Url.Query);
        Assert.Contains("tt0088763", f.Upstream.Requests.Single().Url.PathAndQuery);
    }

    [Fact]
    public async Task Missing_api_key_throws_configuration_exception()
    {
        using var f = new Fixture(apiKey: "");
        f.Upstream.Handler = _ => Json(TmdbTestData.SearchJson);

        await Assert.ThrowsAsync<TmdbConfigurationException>(
            () => f.Client.SearchMoviesAsync("Back to the Future", null, "en-US", includeAdult: false));
        Assert.Empty(f.Upstream.Requests); // fails before any network activity
    }

    [Fact]
    public async Task Query_mode_puts_the_key_in_the_url_but_not_in_the_cache_key()
    {
        using var f = new Fixture(auth: TmdbAuthMode.Query);
        f.Upstream.Handler = _ => Json(TmdbTestData.SearchJson);

        await f.Client.SearchMoviesAsync("Back to the Future", 1985, "en-US", includeAdult: false);

        UpstreamRequest request = Assert.Single(f.Upstream.Requests);
        Assert.Contains("api_key=test-api-key", request.Url.Query);

        // The stored cache row must be keyed by the secret-free URL, not the request URL,
        // so the API key never lands in the cache DB.
        string cleanUrl = request.Url.AbsoluteUri.Replace("&api_key=test-api-key", "");
        CachedUpstreamRow? row = f.Store.GetUpstream(UpstreamCache.ComputeKey(cleanUrl));
        Assert.NotNull(row);
        Assert.Equal(UpstreamCache.ComputeKey(cleanUrl), row!.Key);
        Assert.NotEqual(UpstreamCache.ComputeKey(request.Url.AbsoluteUri), row.Key);
    }

    [Fact]
    public async Task Auto_mode_probes_and_falls_back_to_query_for_legacy_keys()
    {
        using var f = new Fixture(auth: TmdbAuthMode.Auto);
        f.Upstream.Handler = request => request.Url.AbsolutePath.EndsWith("/authentication")
            ? new UpstreamResponse(401, [], null, null, null, null)
            : Json(TmdbTestData.SearchJson);

        await f.Client.SearchMoviesAsync("Back to the Future", null, "en-US", includeAdult: false);

        UpstreamRequest search = f.Upstream.Requests.Single(r => r.Url.AbsolutePath.EndsWith("/search/movie"));
        Assert.Contains("api_key=test-api-key", search.Url.Query);
        Assert.Contains("/authentication", f.Upstream.Requests[0].Url.AbsolutePath); // probe first
    }

    [Fact]
    public async Task Auto_mode_uses_bearer_when_the_key_is_accepted()
    {
        using var f = new Fixture(auth: TmdbAuthMode.Auto);
        f.Upstream.Handler = _ => Json(TmdbTestData.SearchJson);

        await f.Client.SearchMoviesAsync("Back to the Future", null, "en-US", includeAdult: false);

        UpstreamRequest search = f.Upstream.Requests.Single(r => r.Url.AbsolutePath.EndsWith("/search/movie"));
        Assert.Equal("Bearer test-api-key", search.Headers!["Authorization"]);
        Assert.False(search.Url.Query.Contains("api_key", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ImageUrl_builds_full_urls_and_omits_empty_paths()
    {
        using var f = new Fixture();

        Assert.Equal("https://image.tmdb.org/t/p/original/p4.jpg", f.Client.ImageUrl("/p4.jpg"));
        Assert.Null(f.Client.ImageUrl(null));
        Assert.Null(f.Client.ImageUrl(""));
    }

    private static UpstreamResponse Json(string body) =>
        new(200, TestBytes.Of(body), "application/json", null, null, null);
}
