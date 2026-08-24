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
/// normalized `items` table for the /metrics per-kind counts.
/// </summary>
public sealed class CacheWarmer
{
    private readonly TmdbClient _tmdb;
    private readonly MovieProviderService _movies;
    private readonly TvProviderService _tv;
    private readonly ImageCache _images;
    private readonly MetadataCache _items;
    private readonly IUpstreamHttp _http;
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
        IUpstreamHttp http,
        ArrOptions options,
        ILogger<CacheWarmer> logger)
    {
        _tmdb = tmdb;
        _movies = movies;
        _tv = tv;
        _images = images;
        _items = items;
        _http = http;
        _options = options;
        _logger = logger;
    }

    public WarmStatus Status => _status;

    /// <summary>Warms Radarr movies. Returns null when another warm is already running.</summary>
    public Task<WarmResult?> WarmMoviesAsync(CancellationToken cancellationToken = default) =>
        RunAsync("movies", WarmMoviesInnerAsync, cancellationToken);

    private async Task<WarmResult> WarmMoviesInnerAsync(CancellationToken ct)
    {
            if (string.IsNullOrWhiteSpace(_options.RadarrUrl))
                return WarmResult.SkippedRun("movies");

            var client = new ArrClient(_options.RadarrUrl, _options.RadarrApiKey, _http);
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
                    await _movies.GetMovieMetadataAsync(
                        tmdbId.ToString(CultureInfo.InvariantCulture), null, null, token).ConfigureAwait(false);
                    var tmdbMovie = await _tmdb.GetMovieAsync(tmdbId, null, token).ConfigureAwait(false);
                    int warmed = await WarmImageAsync(tmdbMovie.PosterPath, token)
                        + await WarmImageAsync(tmdbMovie.BackdropPath, token);
                    RecordItem("movie", tmdbId, "movie");
                    Interlocked.Add(ref images, warmed);
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

    /// <summary>Warms Sonarr series (show + all seasons + episodes + stills).</summary>
    public Task<WarmResult?> WarmShowsAsync(CancellationToken cancellationToken = default) =>
        RunAsync("shows", WarmShowsInnerAsync, cancellationToken);

    private async Task<WarmResult> WarmShowsInnerAsync(CancellationToken ct)
    {
            if (string.IsNullOrWhiteSpace(_options.SonarrUrl))
                return WarmResult.SkippedRun("shows");

            var client = new ArrClient(_options.SonarrUrl, _options.SonarrApiKey, _http);
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
                    IReadOnlyList<TmdbShowSummary> found =
                        await _tmdb.FindTvByExternalIdAsync("tvdb_id", tvdbId.ToString(CultureInfo.InvariantCulture), null, token)
                            .ConfigureAwait(false);
                    if (found.Count == 0)
                    {
                        Interlocked.Increment(ref missing);
                        return;
                    }

                    int showId = found[0].Id;
                    await _tv.GetShowMetadataAsync(showId.ToString(CultureInfo.InvariantCulture),
                        includeChildren: true, null, null, token).ConfigureAwait(false);

                    TmdbShow show = await _tmdb.GetShowAsync(showId, null, token).ConfigureAwait(false);
                    int warmed = await WarmImageAsync(show.PosterPath, token)
                        + await WarmImageAsync(show.BackdropPath, token);
                    RecordItem("show", showId, "show");
                    Interlocked.Increment(ref items);

                    foreach (TmdbSeasonSummary seasonSummary in show.Seasons ?? [])
                    {
                        TmdbSeason season = await _tmdb.GetSeasonAsync(showId, seasonSummary.SeasonNumber, null, token)
                            .ConfigureAwait(false);
                        warmed += await WarmImageAsync(season.PosterPath, token);
                        RecordItem("season", season.Id, "season", showId);
                        Interlocked.Increment(ref items);

                        foreach (TmdbEpisode episode in season.Episodes ?? [])
                        {
                            warmed += await WarmImageAsync(episode.StillPath, token);
                            RecordItem("episode", episode.Id, "episode", showId);
                            Interlocked.Increment(ref items);
                        }
                    }

                    Interlocked.Add(ref images, warmed);
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    Interlocked.Increment(ref errors);
                    _logger.LogWarning(ex, "Failed to warm series {TvdbId} ({Title})", tvdbId, entry.Title);
                }
            });

        return new WarmResult("shows", items, images, missing, errors, Skipped: false, ElapsedSeconds: 0);
    }

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

    /// <summary>Guards against overlapping runs and publishes the status snapshot.</summary>
    private async Task<WarmResult?> RunAsync(string source, Func<CancellationToken, Task<WarmResult>> body, CancellationToken ct)
    {
        if (!await _gate.WaitAsync(0, ct).ConfigureAwait(false))
            return null;

        try
        {
            var started = DateTimeOffset.UtcNow;
            _status = new WarmStatus(IsRunning: true, LastResult: null);
            WarmResult result = await body(ct).ConfigureAwait(false);
            result = result with { ElapsedSeconds = (DateTimeOffset.UtcNow - started).TotalSeconds };
            _status = new WarmStatus(IsRunning: false, result);
            _logger.LogInformation(
                "Warm {Source} done: {Items} items, {Images} images, {Missing} missing, {Errors} errors in {Elapsed:F1}s",
                source, result.ItemsWarmed, result.ImagesWarmed, result.Missing, result.Errors, result.ElapsedSeconds);
            return result;
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
