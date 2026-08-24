using Metacache.Core.Cache;
using Metacache.Core.Providers;
using Metacache.Host.Tests.Cache;
using Microsoft.Extensions.Logging.Abstractions;

namespace Metacache.Host.Tests.Providers;

public class ArrClientTests
{
    private sealed class Fixture : IDisposable
    {
        public FakeClock Clock { get; } = new(DateTimeOffset.Parse("2026-08-24T00:00:00+00:00"));
        public FakeUpstream Upstream { get; } = new();
        public UpstreamMetrics Metrics { get; } = new();
        public CacheStore Store { get; }
        public UpstreamCache Cache { get; }
        public ArrClient Radarr { get; }
        public ArrClient Sonarr { get; }

        public Fixture()
        {
            Store = new CacheStore(":memory:", Clock);
            Cache = new UpstreamCache(Store, Upstream, new SingleFlight(), Clock, Metrics, NullLogger<UpstreamCache>.Instance);
            Radarr = new ArrClient("http://radarr:7878", "radarr-key", Cache);
            Sonarr = new ArrClient("http://sonarr:8989", "sonarr-key", Cache);
        }

        public void Dispose() => Store.Dispose();
    }

    [Fact]
    public async Task Radarr_movies_are_parsed_and_the_api_key_rides_the_header()
    {
        using var f = new Fixture();
        f.Upstream.Handler = request =>
        {
            Assert.Equal("/api/v3/movie", request.Url.AbsolutePath);
            Assert.Equal("radarr-key", request.Headers!["X-Api-Key"]);
            return new UpstreamResponse(200, TestBytes.Of(TmdbTestData.RadarrMoviesJson), "application/json", null, null, null);
        };

        IReadOnlyList<ArrMovie> movies = await f.Radarr.GetMoviesAsync();

        Assert.Equal(2, movies.Count);
        Assert.Equal(105, movies[0].TmdbId);
        Assert.Equal("Back to the Future", movies[0].Title);
        Assert.Equal(1985, movies[0].Year);
        Assert.Equal(165, movies[1].TmdbId);
    }

    [Fact]
    public async Task Sonarr_series_carry_the_tvdb_id()
    {
        using var f = new Fixture();
        f.Upstream.Handler = request =>
        {
            Assert.Equal("/api/v3/series", request.Url.AbsolutePath);
            return new UpstreamResponse(200, TestBytes.Of(TmdbTestData.SonarrSeriesJson), "application/json", null, null, null);
        };

        IReadOnlyList<ArrSeries> series = await f.Sonarr.GetSeriesAsync();

        ArrSeries first = Assert.Single(series);
        Assert.Equal(152831, first.TvdbId);
        Assert.Equal("Adventure Time", first.Title);
        Assert.Equal(2010, first.Year);
    }

    [Fact]
    public async Task Missing_api_key_throws_before_any_network_activity()
    {
        using var f = new Fixture();
        var client = new ArrClient("http://radarr:7878", "", f.Cache);

        await Assert.ThrowsAsync<ArrConfigurationException>(() => client.GetMoviesAsync());
        Assert.Empty(f.Upstream.Requests);
    }

    [Fact]
    public async Task Upstream_error_status_throws_as_arr_exception()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(401, [], null, null, null, null);
        var client = new ArrClient("http://radarr:7878", "bad-key", f.Cache);

        ArrException ex = await Assert.ThrowsAsync<ArrException>(() => client.GetMoviesAsync());
        Assert.Equal(401, ex.StatusCode);
    }

    [Fact]
    public async Task Arr_requests_are_recorded_in_the_duration_histogram_by_host()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(200, TestBytes.Of(TmdbTestData.RadarrMoviesJson), "application/json", null, null, null);

        await f.Radarr.GetMoviesAsync();
        await f.Radarr.GetMoviesAsync(); // zero-TTL → still revalidates (on-demand freshness)

        ProviderDurationHistogram radarr = Assert.Single(f.Metrics.Snapshot().Histograms);
        Assert.Equal("radarr", radarr.Provider); // host-derived, like tmdb/images
        Assert.Equal(2, radarr.Count);
        Assert.Equal(2, f.Upstream.Requests.Count); // every call reaches the ARR app
    }
}
