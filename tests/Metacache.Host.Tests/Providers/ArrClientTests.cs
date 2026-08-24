using Metacache.Core.Cache;
using Metacache.Core.Providers;
using Metacache.Host.Tests.Cache;

namespace Metacache.Host.Tests.Providers;

public class ArrClientTests
{
    [Fact]
    public async Task Radarr_movies_are_parsed_and_the_api_key_rides_the_header()
    {
        var upstream = new FakeUpstream
        {
            Handler = request =>
            {
                Assert.Equal("/api/v3/movie", request.Url.AbsolutePath);
                Assert.Equal("radarr-key", request.Headers!["X-Api-Key"]);
                return new UpstreamResponse(200, TestBytes.Of(TmdbTestData.RadarrMoviesJson), "application/json", null, null, null);
            }
        };

        var client = new ArrClient("http://radarr:7878", "radarr-key", upstream);
        IReadOnlyList<ArrMovie> movies = await client.GetMoviesAsync();

        Assert.Equal(2, movies.Count);
        Assert.Equal(105, movies[0].TmdbId);
        Assert.Equal("Back to the Future", movies[0].Title);
        Assert.Equal(1985, movies[0].Year);
        Assert.Equal(165, movies[1].TmdbId);
    }

    [Fact]
    public async Task Sonarr_series_carry_the_tvdb_id()
    {
        var upstream = new FakeUpstream
        {
            Handler = request =>
            {
                Assert.Equal("/api/v3/series", request.Url.AbsolutePath);
                return new UpstreamResponse(200, TestBytes.Of(TmdbTestData.SonarrSeriesJson), "application/json", null, null, null);
            }
        };

        var client = new ArrClient("http://sonarr:8989", "sonarr-key", upstream);
        IReadOnlyList<ArrSeries> series = await client.GetSeriesAsync();

        ArrSeries first = Assert.Single(series);
        Assert.Equal(152831, first.TvdbId);
        Assert.Equal("Adventure Time", first.Title);
        Assert.Equal(2010, first.Year);
    }

    [Fact]
    public async Task Missing_api_key_throws_before_any_network_activity()
    {
        var upstream = new FakeUpstream();
        var client = new ArrClient("http://radarr:7878", "", upstream);

        await Assert.ThrowsAsync<ArrConfigurationException>(() => client.GetMoviesAsync());
        Assert.Empty(upstream.Requests);
    }

    [Fact]
    public async Task Upstream_error_status_throws()
    {
        var upstream = new FakeUpstream { Handler = _ => new UpstreamResponse(401, [], null, null, null, null) };
        var client = new ArrClient("http://radarr:7878", "bad-key", upstream);

        ArrException ex = await Assert.ThrowsAsync<ArrException>(() => client.GetMoviesAsync());
        Assert.Equal(401, ex.StatusCode);
    }
}
