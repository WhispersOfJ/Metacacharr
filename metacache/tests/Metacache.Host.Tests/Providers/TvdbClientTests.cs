using System.Net;
using System.Text;
using Metacache.Core.Cache;
using Metacache.Core.Providers;
using Metacache.Host.Tests.Cache;
using Microsoft.Extensions.Logging.Abstractions;

namespace Metacache.Host.Tests.Providers;

public class TvdbClientTests
{
    private sealed class FakeLoginHandler : HttpMessageHandler
    {
        public int LoginCount { get; private set; }
        public int StatusCode { get; set; } = 200;

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            LoginCount++;
            return Task.FromResult(new HttpResponseMessage((HttpStatusCode)StatusCode)
            {
                Content = new StringContent(TmdbTestData.TvdbLoginJson, Encoding.UTF8, "application/json")
            });
        }
    }

    private sealed class Fixture : IDisposable
    {
        public FakeClock Clock { get; } = new(DateTimeOffset.Parse("2026-08-24T00:00:00+00:00"));
        public FakeUpstream Upstream { get; } = new();
        public FakeLoginHandler Login { get; } = new();
        private readonly HttpClient _loginHttp;
        private readonly CacheStore _store;
        public TvdbClient Client { get; }

        public Fixture(string apiKey = "test-tvdb-key")
        {
            _store = new CacheStore(":memory:", Clock);
            var cache = new UpstreamCache(_store, Upstream, new SingleFlight(), Clock, new UpstreamMetrics(),
                NullLogger<UpstreamCache>.Instance);
            _loginHttp = new HttpClient(Login);
            Client = new TvdbClient(
                new TvdbOptions(ApiKey: apiKey, BaseUrl: TmdbTestData.TvdbBaseUrl),
                cache, _loginHttp, Clock, NullLogger<TvdbClient>.Instance);
        }

        public void Dispose()
        {
            _loginHttp.Dispose();
            _store.Dispose();
        }
    }

    private static UpstreamResponse Json(string body) =>
        new(200, TestBytes.Of(body), "application/json", null, null, null);

    private const string EpisodesUrl = "https://api4.thetvdb.com/v4/series/152831/episodes/default";

    [Fact]
    public async Task Episodes_route_through_the_gateway_with_bearer_token_and_parse()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.TvdbEpisodesJson);

        TvdbSeriesEpisodes? series = await f.Client.GetSeriesEpisodesAsync(152831);

        Assert.NotNull(series);
        Assert.Equal("Adventure Time", series!.Series!.Name);
        Assert.Equal(3, series.Episodes!.Count); // count OK (xUnit analyzer allows non-1 counts)

        TvdbEpisode first = series.Episodes[0];
        Assert.Equal(7100001, first.Id);
        Assert.Equal("Slumber Party Panic", first.Name);
        Assert.Equal(1, first.SeasonNumber);
        Assert.Equal(1, first.Number);
        Assert.Equal("2010-04-05", first.Aired);
        Assert.Equal("https://artworks.thetvdb.com/banners/episodes/152831/7100001.jpg", first.Image);

        UpstreamRequest request = Assert.Single(f.Upstream.Requests);
        Assert.Equal(EpisodesUrl, request.Url.AbsoluteUri);
        Assert.Equal("Bearer tvdb-test-token", request.Headers!["Authorization"]);
        Assert.Equal(1, f.Login.LoginCount);
    }

    [Fact]
    public async Task Login_happens_once_and_the_token_is_reused()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.TvdbEpisodesJson);

        await f.Client.GetSeriesEpisodesAsync(152831);
        await f.Client.GetSeriesEpisodesAsync(9999); // different series → a second upstream call

        Assert.Equal(1, f.Login.LoginCount);
        Assert.Equal(2, f.Upstream.Requests.Count);
    }

    [Fact]
    public async Task Data_call_401_reauthenticates_and_retries_once()
    {
        using var f = new Fixture();
        int calls = 0;
        f.Upstream.Handler = _ => ++calls == 1
            ? new UpstreamResponse(401, TestBytes.Of("""{ "status": "error" }"""), "application/json", null, null, null)
            : Json(TmdbTestData.TvdbEpisodesJson);

        TvdbSeriesEpisodes? series = await f.Client.GetSeriesEpisodesAsync(152831);

        Assert.NotNull(series);
        Assert.Equal("Adventure Time", series!.Series!.Name);
        Assert.Equal(2, calls); // 401 then success
        Assert.Equal(2, f.Login.LoginCount); // original login + re-login after the 401
    }

    [Fact]
    public async Task Episodes_are_cached_until_ttl()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Json(TmdbTestData.TvdbEpisodesJson);

        await f.Client.GetSeriesEpisodesAsync(152831);
        await f.Client.GetSeriesEpisodesAsync(152831);

        Assert.Single(f.Upstream.Requests); // second call served from cache
        Assert.Equal(1, f.Login.LoginCount);
    }

    [Fact]
    public async Task Unknown_series_returns_null()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(404, TestBytes.Of("""{ "status": "error" }"""), "application/json", null, null, null);

        TvdbSeriesEpisodes? series = await f.Client.GetSeriesEpisodesAsync(999999);

        Assert.Null(series);
    }

    [Fact]
    public async Task Missing_key_throws_TvdbConfigurationException_without_network_activity()
    {
        using var f = new Fixture(apiKey: "");
        f.Upstream.Handler = _ => Json(TmdbTestData.TvdbEpisodesJson);

        await Assert.ThrowsAsync<TvdbConfigurationException>(() => f.Client.GetSeriesEpisodesAsync(152831));

        Assert.Equal(0, f.Login.LoginCount);
        Assert.Empty(f.Upstream.Requests);
    }
}
