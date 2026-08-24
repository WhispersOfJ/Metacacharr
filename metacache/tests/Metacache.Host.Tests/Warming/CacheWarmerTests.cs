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
            .AddTvdbClient(new TvdbOptions(ApiKey: "test-tvdb-key", BaseUrl: TmdbTestData.TvdbBaseUrl))
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
        Assert.StartsWith("/img/", Store.GetItem("movie-105", "en-US")!.Thumb); // browse thumb (§21)

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

        // Plex asks for episode metadata via the dedicated episode endpoint — warmed too.
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.EndsWith("/tv/15260/season/1/episode/1", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Unconfigured_source_is_skipped_without_network_activity()
    {
        var options = new ArrOptions(); // blank URLs
        await using var services = new ServiceCollection()
            .AddMetacacheCache(new CacheOptions(":memory:", _imageDir, 20L * 1024 * 1024, 10L * 1024 * 1024 * 1024))
            .AddMetacacheMatching(new ConfigurationBuilder().Build())
            .AddTmdbClient(new TmdbOptions(ApiKey: "k", BaseUrl: TmdbTestData.BaseUrl, Auth: TmdbAuthMode.Bearer))
            .AddTvdbClient(new TvdbOptions(ApiKey: "k", BaseUrl: TmdbTestData.TvdbBaseUrl))
            .AddMetacachePlexProviders()
            .AddMetacacheWarming(options)
            .AddSingleton<IUpstreamHttp>(new FakeUpstream())
            .AddLogging()
            .BuildServiceProvider();

        WarmResult result = (await services.GetRequiredService<CacheWarmer>().WarmMoviesAsync())!;

        Assert.True(result.Skipped);
        Assert.Equal(0, result.ItemsWarmed);
    }

    [Fact]
    public async Task Failed_warm_resets_the_running_flag_and_releases_the_gate()
    {
        _upstream.Route(arrMovies: TmdbTestData.RadarrMoviesJson);
        CacheWarmer warmer = Warmer;

        // tmdb 999999999 → upstream 404 → the warm throws (regression: status stuck at isRunning).
        await Assert.ThrowsAsync<TmdbNotFoundException>(() => warmer.WarmMovieAsync(999999999));
        Assert.False(warmer.Status.IsRunning);

        // A crashed warm still publishes a failed last result, so the Prometheus
        // warm_failed alert has a series to key off (regression: null hid it).
        WarmResult? failed = warmer.Status.LastResult;
        Assert.NotNull(failed);
        Assert.Equal(1, failed!.Errors);
        Assert.Equal("movie", failed.Source);
        Assert.False(failed.Skipped);

        // The gate was released: a subsequent warm still runs.
        WarmResult? retry = await warmer.WarmMovieAsync(105);
        Assert.NotNull(retry);
        Assert.Equal(1, retry!.ItemsWarmed);
    }

    // ---- predictive warm (§20) ----

    [Fact]
    public async Task Predictive_movie_warm_warms_played_and_similar_titles()
    {
        _upstream.Route();
        var play = new PlexPlayMetadata(
            Kind: "movie", Title: null, Year: null, Guids: ["tmdb://105"], ShowTitle: null, Season: null, Episode: null);

        WarmResult result = (await Warmer.WarmPredictiveAsync(play))!;

        Assert.Equal("predictive", result.Source);
        Assert.Equal(3, result.ItemsWarmed); // played 105 + similar 165 + 999
        Assert.Equal(5, result.ImagesWarmed); // poster + backdrop each (999 has no backdrop)
        Assert.Equal(0, result.Missing);
        Assert.Equal(0, result.Errors);
        Assert.Equal(3, Store.CountItemsByKind()["movie"]);
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.EndsWith("/movie/105/similar", StringComparison.Ordinal));

        WarmResult status = Assert.IsType<WarmResult>(Warmer.Status.LastResult);
        Assert.Equal("predictive", status.Source);
    }

    [Fact]
    public async Task Predictive_episode_warm_warms_show_next_episodes_and_similar_show()
    {
        _upstream.Route();
        var play = new PlexPlayMetadata(
            Kind: "episode", Title: null, Year: null, Guids: [],
            ShowTitle: "Adventure Time", Season: 1, Episode: 1);

        WarmResult result = (await Warmer.WarmPredictiveAsync(play))!;

        // Show card + season 1 + played & next episode (1,1)/(1,2) + similar show 1399 card.
        Assert.Equal(5, result.ItemsWarmed);
        Assert.Equal(0, result.Missing);
        Assert.Equal(0, result.Errors);
        Assert.Equal(2, Store.CountItemsByKind()["show"]); // 15260 + similar 1399
        Assert.Equal(1, Store.CountItemsByKind()["season"]);
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.EndsWith("/tv/15260/season/1/episode/1", StringComparison.Ordinal));
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.EndsWith("/tv/15260/season/1/episode/2", StringComparison.Ordinal));
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.EndsWith("/tv/15260/similar", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Predictive_finale_play_primes_the_next_season()
    {
        _upstream.Route();
        // Season 1's last episode (1,2) → also warm season 2 + its first episode.
        var play = new PlexPlayMetadata(
            Kind: "episode", Title: null, Year: null, Guids: [],
            ShowTitle: "Adventure Time", Season: 1, Episode: 2);

        WarmResult result = (await Warmer.WarmPredictiveAsync(play))!;

        // Show + season 1 + episode (1,2) + season 2 + episode (2,1) + similar show = 6.
        Assert.Equal(6, result.ItemsWarmed);
        Assert.Equal(2, Store.CountItemsByKind()["season"]);
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.EndsWith("/tv/15260/season/2", StringComparison.Ordinal));
        Assert.Contains(_upstream.Requests, r => r.Url.AbsolutePath.EndsWith("/tv/15260/season/2/episode/1", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Predictive_unresolvable_item_reports_missing_without_warming()
    {
        _upstream.Route();
        var play = new PlexPlayMetadata(
            Kind: "movie", Title: "Explicit", Year: null, Guids: [], ShowTitle: null, Season: null, Episode: null);

        WarmResult result = (await Warmer.WarmPredictiveAsync(play))!;

        Assert.Equal(1, result.Missing);
        Assert.Equal(0, result.ItemsWarmed);
        Assert.Empty(Store.CountItemsByKind());
    }

    [Fact]
    public async Task Multi_language_warm_stores_items_in_each_language()
    {
        var options = new ArrOptions(
            RadarrUrl: "http://radarr:7878", RadarrApiKey: "radarr-key",
            SonarrUrl: "", SonarrApiKey: "",
            Concurrency: 2);
        var warmOpts = new WarmOptions(Languages: ["en-US", "de-DE"]);
        var upstream = new FakeUpstream();
        upstream.Route(arrMovies: TmdbTestData.RadarrMoviesJson);

        using var services = new ServiceCollection()
            .AddMetacacheCache(new CacheOptions(":memory:", _imageDir, 20L * 1024 * 1024, 10L * 1024 * 1024 * 1024))
            .AddMetacacheMatching(new ConfigurationBuilder().Build())
            .AddTmdbClient(new TmdbOptions(ApiKey: "test-api-key", BaseUrl: TmdbTestData.BaseUrl, Auth: TmdbAuthMode.Bearer))
            .AddTvdbClient(new TvdbOptions(ApiKey: "test-tvdb-key", BaseUrl: TmdbTestData.TvdbBaseUrl))
            .AddMetacachePlexProviders()
            .AddMetacacheWarming(options, warmOpts)
            .AddSingleton<IUpstreamHttp>(upstream)
            .AddLogging()
            .BuildServiceProvider();

        CacheWarmer warmer = services.GetRequiredService<CacheWarmer>();
        WarmResult result = (await warmer.WarmMoviesAsync())!;

        Assert.True(result.ItemsWarmed >= 2, $"Expected >= 2 items (1 movie × 2 langs), got {result.ItemsWarmed}");

        // Each movie should have items in both en-US and de-DE
        var store = services.GetRequiredService<CacheStore>();
        var allItems = store.SearchItems(new ItemSearch(Limit: 500), DateTimeOffset.UtcNow);
        var movieItems = allItems.Items.Where(i => i.Kind == "movie").ToList();
        var enItems = movieItems.Where(i => i.Lang == "en-US").ToList();
        var deItems = movieItems.Where(i => i.Lang == "de-DE").ToList();
        Assert.True(enItems.Count >= 1, "Expected at least 1 en-US movie item");
        Assert.True(deItems.Count >= 1, "Expected at least 1 de-DE movie item");
    }
}
