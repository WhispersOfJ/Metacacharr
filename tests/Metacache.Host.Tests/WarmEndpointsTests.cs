using System.Net.Http.Json;
using System.Text.Json;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests;

/// <summary>
/// Boots the real host with fake Radarr/Sonarr + TMDB upstreams and exercises the
/// /warm/* endpoints end to end (DI wiring and the warmer's real run included).
/// </summary>
public class WarmEndpointsTests : IDisposable
{
    private readonly FakeUpstream _upstream = new();
    private readonly WebApplicationFactory<Program> _factory;
    private readonly string _imageDir;

    public WarmEndpointsTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-warm-host-{Guid.NewGuid():N}");
        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("Metacache:DataPath", ":memory:");
                builder.UseSetting("Metacache:Images:Directory", _imageDir);
                builder.UseSetting("Metacache:Tmdb:ApiKey", "test-api-key");
                builder.UseSetting("Metacache:Tmdb:Auth", "Bearer");
                builder.UseSetting("Metacache:Arr:RadarrUrl", "http://radarr:7878");
                builder.UseSetting("Metacache:Arr:RadarrApiKey", "radarr-key");
                builder.UseSetting("Metacache:Arr:SonarrUrl", "http://sonarr:8989");
                builder.UseSetting("Metacache:Arr:SonarrApiKey", "sonarr-key");
                builder.ConfigureTestServices(services => services.AddSingleton<IUpstreamHttp>(_upstream));
            });
        _upstream.Route(arrMovies: TmdbTestData.RadarrMoviesJson, arrSeries: TmdbTestData.SonarrSeriesJson);
    }

    public void Dispose()
    {
        _factory.Dispose();
        if (Directory.Exists(_imageDir))
            Directory.Delete(_imageDir, recursive: true);
    }

    private HttpClient Client => _factory.CreateClient();

    [Fact]
    public async Task Warm_movies_endpoint_runs_the_warmer_and_reports()
    {
        var response = await Client.PostAsync("/warm/movies", null);

        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);
        JsonDocument doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        JsonElement root = doc.RootElement;
        Assert.Equal("movies", root.GetProperty("source").GetString());
        Assert.Equal(2, root.GetProperty("itemsWarmed").GetInt32());
        Assert.Equal(4, root.GetProperty("imagesWarmed").GetInt32());
        Assert.Equal(0, root.GetProperty("errors").GetInt32());
        Assert.True(root.GetProperty("elapsedSeconds").GetDouble() >= 0);

        // The cache now holds the warmed items: per-kind rows + upstream entries.
        var store = _factory.Services.GetRequiredService<CacheStore>();
        Assert.Equal(2, store.CountItemsByKind()["movie"]);
        Assert.True(store.GetStats().UpstreamEntries >= 2);
    }

    [Fact]
    public async Task Warm_shows_endpoint_warms_the_whole_hierarchy()
    {
        var response = await Client.PostAsync("/warm/shows", null);

        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);
        JsonDocument doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        JsonElement root = doc.RootElement;
        Assert.Equal("shows", root.GetProperty("source").GetString());
        Assert.Equal(6, root.GetProperty("itemsWarmed").GetInt32());
        Assert.Equal(7, root.GetProperty("imagesWarmed").GetInt32());

        var store = _factory.Services.GetRequiredService<CacheStore>();
        IReadOnlyDictionary<string, int> byKind = store.CountItemsByKind();
        Assert.Equal(1, byKind["show"]);
        Assert.Equal(2, byKind["season"]);
        Assert.Equal(3, byKind["episode"]);
    }

    [Fact]
    public async Task Warm_status_reports_the_last_run()
    {
        var before = JsonDocument.Parse(await Client.GetStringAsync("/warm/status"));
        Assert.False(before.RootElement.GetProperty("isRunning").GetBoolean());

        await Client.PostAsync("/warm/all", null);

        var after = JsonDocument.Parse(await Client.GetStringAsync("/warm/status"));
        JsonElement root = after.RootElement;
        Assert.False(root.GetProperty("isRunning").GetBoolean());
        JsonElement last = root.GetProperty("lastResult");
        Assert.Equal("all", last.GetProperty("source").GetString());
        Assert.True(last.GetProperty("itemsWarmed").GetInt32() > 0);
    }
}
