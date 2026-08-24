using System.Globalization;
using Microsoft.Extensions.Logging;
using Metacache.Core.Cache;
using Metacache.Core.Providers;

namespace Metacache.Plex.Warming;

/// <summary>
/// M3 cache warming (DESIGN.md §8): turns the ARR apps' libraries into the cache
/// inventory. Radarr movies and Sonarr series are resolved through TMDB (via the
/// cached provider services, so every fetch lands in the store), their artwork is
/// pulled through <see cref="ImageCache"/>, and each item gets a row in the
/// normalized `items` table for the /metrics per-kind counts. The single-item
/// methods back the /webhook endpoints (event-driven warm on new imports) and the
/// scheduled nightly warm reuses the full-library runs.
/// </summary>
public sealed class CacheWarmer
{
    private readonly TmdbClient _tmdb;
    private readonly MovieProviderService _movies;
    private readonly TvProviderService _tv;
    private readonly ImageCache _images;
    private readonly MetadataCache _items;
    private readonly UpstreamCache _upstream;
    private readonly ArrOptions _options;
    private readonly ILogger<CacheWarmer> _logger;

    private readonly SemaphoreSlim _gate = new(1, 1);
    private WarmStatus _status = new(IsRunning: false, LastResult: null);

    public CacheWarmer(
        TmdbClient tmdb,
        MovieProviderService movies,
        TvProviderService tv,
        ImageCache images,
        MetadataCache items,
        UpstreamCache upstream,
        ArrOptions options,
        ILogger<CacheWarmer> logger)
    {
        _tmdb = tmdb;
        _movies = movies;
        _tv = tv;
        _images = images;
        _items = items;
        _upstream = upstream;
        _options = options;
        _logger = logger;
    }

    public WarmStatus Status => _status;

    // ---- full-library runs (scheduled / manual) ----

    /// <summary>Warms every Radarr movie. Returns null when another warm is running.</summary>
    public Task<WarmResult?> WarmMoviesAsync(CancellationToken cancellationToken = default) =>
        RunAsync("movies", WarmMoviesInnerAsync, cancellationToken);

    /// <summary>Warms every Sonarr series. Returns null when another warm is running.</summary>
    public Task<WarmResult?> WarmShowsAsync(CancellationToken cancellationToken = default) =>
        RunAsync("shows", WarmShowsInnerAsync, cancellationToken);

    /// <summary>Warms both sources (movies first, then shows) as one published run.</summary>
    public Task<WarmResult?> WarmAllAsync(CancellationToken cancellationToken = default) =>
        RunAsync("all", async ct =>
        {
            if (string.IsNullOrWhiteSpace(_options.RadarrUrl) && string.IsNullOrWhiteSpace(_options.SonarrUrl))
                return WarmResult.SkippedRun("all");

            WarmResult movies = await WarmMoviesInnerAsync(ct).ConfigureAwait(false);
            WarmResult shows = await WarmShowsInnerAsync(ct).ConfigureAwait(false);
            return new WarmResult(
                "all",
                movies.ItemsWarmed + shows.ItemsWarmed,
                movies.ImagesWarmed + shows.ImagesWarmed,
                movies.Missing + shows.Missing,
                movies.Errors + shows.Errors,
                Skipped: false,
                ElapsedSeconds: movies.ElapsedSeconds + shows.ElapsedSeconds);
        }, cancellationToken);

    // ---- single-item runs (event-driven /webhook) ----

    /// <summary>Warms one Radarr movie by tmdbId. Returns null when another warm is running.</summary>
    public Task<WarmResult?> WarmMovieAsync(int tmdbId, CancellationToken cancellationToken = default) =>
        RunAsync("movie", async ct =>
        {
            int images = await WarmOneMovieAsync(tmdbId, ct).ConfigureAwait(false);
            return new WarmResult("movie", ItemsWarmed: 1, images, Missing: 0, Errors: 0, Skipped: false, ElapsedSeconds: 0);
        }, cancellationToken);

    /// <summary>Warms one Sonarr series by tvdbId (show + all seasons + episodes). Returns null when another warm is running.</summary>
    public Task<WarmResult?> WarmShowByTvdbAsync(int tvdbId, CancellationToken cancellationToken = default) =>
        RunAsync("show", async ct =>
        {
            (bool found, int items, int images) = await WarmOneShowByTvdbAsync(tvdbId, ct).ConfigureAwait(false);
            return found
                ? new WarmResult("show", items, images, Missing: 0, Errors: 0, Skipped: false, ElapsedSeconds: 0)
                : new WarmResult("show", ItemsWarmed: 0, ImagesWarmed: 0, Missing: 1, Errors: 0, Skipped: false, ElapsedSeconds: 0);
        }, cancellationToken);

    // ---- internals ----

    private async Task<WarmResult> WarmMoviesInnerAsync(CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(_options.RadarrUrl))
            return WarmResult.SkippedRun("movies");

        var client = new ArrClient(_options.RadarrUrl, _options.RadarrApiKey, _upstream);
        IReadOnlyList<ArrMovie> movies = await client.GetMoviesAsync(ct).ConfigureAwait(false);
        _logger.LogInformation("Warming {Count} movies from Radarr", movies.Count);

        int items = 0, images = 0, missing = 0, errors = 0;
        await Parallel.ForEachAsync(movies, new ParallelOptions
        {
            MaxDegreeOfParallelism = Math.Max(1, _options.Concurrency),
            CancellationToken = ct
        }, async (movie, token) =>
        {
            if (movie.TmdbId is not { } tmdbId)
            {
                Interlocked.Increment(ref missing);
                return;
            }

            try
            {
                Interlocked.Add(ref images, await WarmOneMovieAsync(tmdbId, token).ConfigureAwait(false));
                Interlocked.Increment(ref items);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                Interlocked.Increment(ref errors);
                _logger.LogWarning(ex, "Failed to warm movie {TmdbId} ({Title})", tmdbId, movie.Title);
            }
        });

        return new WarmResult("movies", items, images, missing, errors, Skipped: false, ElapsedSeconds: 0);
    }

    private async Task<WarmResult> WarmShowsInnerAsync(CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(_options.SonarrUrl))
            return WarmResult.SkippedRun("shows");

        var client = new ArrClient(_options.SonarrUrl, _options.SonarrApiKey, _upstream);
        IReadOnlyList<ArrSeries> series = await client.GetSeriesAsync(ct).ConfigureAwait(false);
        _logger.LogInformation("Warming {Count} series from Sonarr", series.Count);

        int items = 0, images = 0, missing = 0, errors = 0;
        await Parallel.ForEachAsync(series, new ParallelOptions
        {
            MaxDegreeOfParallelism = Math.Max(1, _options.Concurrency),
            CancellationToken = ct
        }, async (entry, token) =>
        {
            if (entry.TvdbId is not { } tvdbId)
            {
                Interlocked.Increment(ref missing);
                return;
            }

            try
            {
                (bool found, int itemCount, int imageCount) = await WarmOneShowByTvdbAsync(tvdbId, token).ConfigureAwait(false);
                if (!found)
                {
                    Interlocked.Increment(ref missing);
                    return;
                }
                Interlocked.Add(ref items, itemCount);
                Interlocked.Add(ref images, imageCount);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                Interlocked.Increment(ref errors);
                _logger.LogWarning(ex, "Failed to warm series {TvdbId} ({Title})", tvdbId, entry.Title);
            }
        });

        return new WarmResult("shows", items, images, missing, errors, Skipped: false, ElapsedSeconds: 0);
    }

    /// <summary>Warms one movie's metadata + artwork. Returns the number of images warmed.</summary>
    private async Task<int> WarmOneMovieAsync(int tmdbId, CancellationToken ct)
    {
        await _movies.GetMovieMetadataAsync(
            tmdbId.ToString(CultureInfo.InvariantCulture), null, null, ct).ConfigureAwait(false);
        TmdbMovie movie = await _tmdb.GetMovieAsync(tmdbId, null, ct).ConfigureAwait(false);
        int images = await WarmImageAsync(movie.PosterPath, ct).ConfigureAwait(false)
            + await WarmImageAsync(movie.BackdropPath, ct).ConfigureAwait(false);
        RecordItem("movie", tmdbId, "movie");
        return images;
    }

    /// <summary>Warms one show by tvdbId: show metadata + every season/episode + artwork.</summary>
    private async Task<(bool Found, int Items, int Images)> WarmOneShowByTvdbAsync(int tvdbId, CancellationToken ct)
    {
        IReadOnlyList<TmdbShowSummary> found =
            await _tmdb.FindTvByExternalIdAsync("tvdb_id", tvdbId.ToString(CultureInfo.InvariantCulture), null, ct)
                .ConfigureAwait(false);
        if (found.Count == 0)
            return (Found: false, 0, 0);

        int showId = found[0].Id;
        await _tv.GetShowMetadataAsync(showId.ToString(CultureInfo.InvariantCulture),
            includeChildren: true, null, null, ct).ConfigureAwait(false);

        TmdbShow show = await _tmdb.GetShowAsync(showId, null, ct).ConfigureAwait(false);
        int images = await WarmImageAsync(show.PosterPath, ct).ConfigureAwait(false)
            + await WarmImageAsync(show.BackdropPath, ct).ConfigureAwait(false);
        RecordItem("show", showId, "show");
        int items = 1;

        foreach (TmdbSeasonSummary seasonSummary in show.Seasons ?? [])
        {
            TmdbSeason season = await _tmdb.GetSeasonAsync(showId, seasonSummary.SeasonNumber, null, ct).ConfigureAwait(false);
            images += await WarmImageAsync(season.PosterPath, ct).ConfigureAwait(false);
            RecordItem("season", season.Id, "season", showId);
            items++;

            foreach (TmdbEpisode episode in season.Episodes ?? [])
            {
                // Plex asks for episode metadata via the dedicated episode endpoint, so
                // warm it too — otherwise the first refresh pays one call per episode.
                await _tmdb.GetEpisodeAsync(showId, episode.SeasonNumber, episode.EpisodeNumber, null, ct).ConfigureAwait(false);
                images += await WarmImageAsync(episode.StillPath, ct).ConfigureAwait(false);
                RecordItem("episode", episode.Id, "episode", showId);
                items++;
            }
        }

        return (Found: true, items, images);
    }

    /// <summary>Guards against overlapping runs and publishes the status snapshot.</summary>
    private async Task<WarmResult?> RunAsync(string source, Func<CancellationToken, Task<WarmResult>> body, CancellationToken ct)
    {
        if (!await _gate.WaitAsync(0, ct).ConfigureAwait(false))
            return null;

        try
        {
            var started = DateTimeOffset.UtcNow;
            // While running, keep the previous result and completion time: the last
            // finished attempt is still the last one until this run lands. Nulling it
            // made the warm gauges vanish for the whole run (hours on big libraries),
            // resetting the MetacacheWarmFailed alert timer.
            _status = new WarmStatus(IsRunning: true, LastResult: _status.LastResult, CompletedAt: _status.CompletedAt);
            try
            {
                WarmResult result = await body(ct).ConfigureAwait(false);
                result = result with { ElapsedSeconds = (DateTimeOffset.UtcNow - started).TotalSeconds };
                _status = new WarmStatus(IsRunning: false, result, CompletedAt: DateTimeOffset.UtcNow);
                _logger.LogInformation(
                    "Warm {Source} done: {Items} items, {Images} images, {Missing} missing, {Errors} errors in {Elapsed:F1}s",
                    source, result.ItemsWarmed, result.ImagesWarmed, result.Missing, result.Errors, result.ElapsedSeconds);
                return result;
            }
            catch (Exception ex)
            {
                // A failed warm must not leave /warm/status stuck at isRunning: true.
                // CompletedAt moves forward, and a failed last result (Errors = 1) is
                // published so /metrics/prometheus renders the warm-errors gauge and
                // the MetacacheWarmFailed alert has a series to key off — a crashed
                // run with LastResult: null was invisible to the rules file.
                var failed = new WarmResult(source, ItemsWarmed: 0, ImagesWarmed: 0, Missing: 0, Errors: 1,
                    Skipped: false, ElapsedSeconds: (DateTimeOffset.UtcNow - started).TotalSeconds);
                _status = new WarmStatus(IsRunning: false, failed, CompletedAt: DateTimeOffset.UtcNow);
                _logger.LogError(ex, "Warm {Source} failed", source);
                throw;
            }
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task<int> WarmImageAsync(string? path, CancellationToken ct)
    {
        if (path is null)
            return 0;
        string? url = _tmdb.ImageUrl(path);
        if (url is null)
            return 0;
        await _images.GetOrFetchAsync(url, ct).ConfigureAwait(false);
        return 1;
    }

    private void RecordItem(string kind, int sourceId, string idKind, int? parentId = null)
    {
        string id = parentId is null
            ? $"{idKind}-{sourceId.ToString(CultureInfo.InvariantCulture)}"
            : $"{idKind}-{parentId.Value.ToString(CultureInfo.InvariantCulture)}-{sourceId.ToString(CultureInfo.InvariantCulture)}";
        var now = DateTimeOffset.UtcNow;
        _items.Put(new CachedItem(
            Id: id,
            Kind: kind,
            Source: "tmdb",
            SourceId: sourceId.ToString(CultureInfo.InvariantCulture),
            Lang: "en-US",
            Json: "{}",
            FetchedAt: now,
            ExpiresAt: now.AddDays(1),
            ETag: null));
    }
}
