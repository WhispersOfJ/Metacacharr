using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Core.Providers;
using Metacache.Host.Tests.Cache;
using Metacache.Plex;
using Metacache.Plex.Warming;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests.Warming;

public class CacheWarmerTests : IDisposable
{
    private readonly FakeUpstream _upstream = new();
    private readonly ServiceProvider _services;
    private readonly string _imageDir;

    public CacheWarmerTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-warm-{Guid.NewGuid():N}");
        var options = new ArrOptions(
            RadarrUrl: "http://radarr:7878", RadarrApiKey: "radarr-key",
            SonarrUrl: "http://sonarr:8989", SonarrApiKey: "sonarr-key",
            Concurrency: 2);
        _services = new ServiceCollection()
            .AddMetacacheCache(new CacheOptions(":memory:", _imageDir, 20L * 1024 * 1024, 10L * 1024 * 1024 * 1024))
            .AddMetacacheMatching(new ConfigurationBuilder().Build())
            .AddTmdbClient(new TmdbOptions(ApiKey: "test-api-key", BaseUrl: TmdbTestData.BaseUrl,
                Auth: TmdbAuthMode.Bearer))
            .AddMetacachePlexProviders()
            .AddMetacacheWarming(options)
            .AddSingleton<IUpstreamHttp>(_upstream)
            .AddLogging()
            .BuildServiceProvider();
    }

    public void Dispose()
    {
        _services.Dispose();
        if (Directory.Exists(_imageDir))
            Directory.Delete(_imageDir, recursive: true);
    }

    private CacheWarmer Warmer => _services.GetRequiredService<CacheWarmer>();
    private CacheStore Store => _services.GetRequiredService<CacheStore>();

    [Fact]
    public async Task Warm_movies_populates_cache_images_and_item_rows()
    {
        _upstream.Route(arrMovies: TmdbTestData.RadarrMoviesJson);

        WarmResult result = (await Warmer.WarmMoviesAsync())!;

        Assert.False(result.Skipped);
        Assert.Equal(2, result.ItemsWarmed);
        Assert.Equal(4, result.ImagesWarmed); // poster + backdrop per movie
        Assert.Equal(0, result.Missing);
        Assert.Equal(0, result.Errors);

        Assert.Equal(2, Store.CountItemsByKind()["movie"]);
        Assert.True(Store.GetStats().UpstreamEntries >= 2, "movie details should be cached");

        // Artwork was actually pulled through the image cache.
        Assert.True(Store.GetStats().UrlEntries >= 4);
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.Contains("/movie/105", StringComparison.Ordinal));
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.StartsWith("/t/p/", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Warm_shows_populates_show_season_episode_rows_and_stills()
    {
        _upstream.Route(arrSeries: TmdbTestData.SonarrSeriesJson);

        WarmResult result = (await Warmer.WarmShowsAsync())!;

        Assert.False(result.Skipped);
        Assert.Equal(6, result.ItemsWarmed); // 1 show + 2 seasons + 3 episodes
        Assert.Equal(7, result.ImagesWarmed); // show poster+backdrop, 2 season posters, 3 stills
        Assert.Equal(0, result.Missing);
        Assert.Equal(0, result.Errors);

        IReadOnlyDictionary<string, int> byKind = Store.CountItemsByKind();
        Assert.Equal(1, byKind["show"]);
        Assert.Equal(2, byKind["season"]);
        Assert.Equal(3, byKind["episode"]);
    }

    [Fact]
    public async Task Unconfigured_source_is_skipped_without_network_activity()
    {
        var options = new ArrOptions(); // blank URLs
        await using var services = new ServiceCollection()
            .AddMetacacheCache(new CacheOptions(":memory:", _imageDir, 20L * 1024 * 1024, 10L * 1024 * 1024 * 1024))
            .AddMetacacheMatching(new ConfigurationBuilder().Build())
            .AddTmdbClient(new TmdbOptions(ApiKey: "k", BaseUrl: TmdbTestData.BaseUrl, Auth: TmdbAuthMode.Bearer))
            .AddMetacachePlexProviders()
            .AddMetacacheWarming(options)
            .AddSingleton<IUpstreamHttp>(new FakeUpstream())
            .AddLogging()
            .BuildServiceProvider();

        WarmResult result = (await services.GetRequiredService<CacheWarmer>().WarmMoviesAsync())!;

        Assert.True(result.Skipped);
        Assert.Equal(0, result.ItemsWarmed);
    }
}
