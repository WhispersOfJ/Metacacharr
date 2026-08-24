using System.Globalization;
using Microsoft.Extensions.Logging;
using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Core.Providers;
using Metacache.Plex.Models;

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
    /// <summary>How many "next" episodes are warmed after the played one (the autoplay queue).</summary>
    private const int NextEpisodesToWarm = 4;

    /// <summary>How many similar titles are warmed per play event (the "related" set).</summary>
    private const int SimilarDepth = 3;

    /// <summary>How many episodes of the *next* season are primed when the played one is a season finale.</summary>
    private const int NextSeasonPriming = 2;

    private readonly TmdbClient _tmdb;
    private readonly MovieProviderService _movies;
    private readonly TvProviderService _tv;
    private readonly GuidLookupService _lookup;
    private readonly ImageCache _images;
    private readonly MetadataCache _items;
    private readonly UpstreamCache _upstream;
    private readonly ArrOptions _options;
    private readonly IReadOnlyList<string> _languages;
    private readonly ILogger<CacheWarmer> _logger;

    private readonly SemaphoreSlim _gate = new(1, 1);
    private WarmStatus _status = new(IsRunning: false, LastResult: null);
    private WarmProgress? _progress;

    public CacheWarmer(
        TmdbClient tmdb,
        MovieProviderService movies,
        TvProviderService tv,
        GuidLookupService lookup,
        ImageCache images,
        MetadataCache items,
        UpstreamCache upstream,
        ArrOptions options,
        WarmOptions warmOptions,
        ILogger<CacheWarmer> logger)
    {
        _tmdb = tmdb;
        _movies = movies;
        _tv = tv;
        _lookup = lookup;
        _images = images;
        _items = items;
        _upstream = upstream;
        _options = options;
        _languages = warmOptions.EffectiveLanguages;
        _logger = logger;
    }

    public WarmStatus Status => _status;
    public WarmProgress? Progress => _progress;

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
            int totalImages = 0, totalItems = 0;
            foreach (string lang in _languages)
            {
                totalImages += await WarmOneMovieAsync(tmdbId, lang, ct).ConfigureAwait(false);
                totalItems++;
            }
            return new WarmResult("movie", ItemsWarmed: totalItems, totalImages, Missing: 0, Errors: 0, Skipped: false, ElapsedSeconds: 0);
        }, cancellationToken);

    /// <summary>Warms one Sonarr series by tvdbId (show + all seasons + episodes). Returns null when another warm is running.</summary>
    public Task<WarmResult?> WarmShowByTvdbAsync(int tvdbId, CancellationToken cancellationToken = default) =>
        RunAsync("show", async ct =>
        {
            int totalItems = 0, totalImages = 0;
            bool anyFound = false;
            foreach (string lang in _languages)
            {
                (bool found, int items, int images) = await WarmOneShowByTvdbAsync(tvdbId, lang, ct).ConfigureAwait(false);
                if (found)
                {
                    anyFound = true;
                    totalItems += items;
                    totalImages += images;
                }
            }
            return anyFound
                ? new WarmResult("show", totalItems, totalImages, Missing: 0, Errors: 0, Skipped: false, ElapsedSeconds: 0)
                : new WarmResult("show", ItemsWarmed: 0, ImagesWarmed: 0, Missing: 1, Errors: 0, Skipped: false, ElapsedSeconds: 0);
        }, cancellationToken);

    // ---- predictive warm (the /webhook/plex playback-start path, §20) ----

    /// <summary>
    /// Predictive warm on a playback-start event: resolves the played item (guid first,
    /// then title matching), warms it, the next episodes (TV) and up to
    /// <see cref="SimilarDepth"/> similar titles. Returns null when another warm is
    /// running — the webhook answers 409 then, same as the ARR webhooks.
    /// </summary>
    public Task<WarmResult?> WarmPredictiveAsync(PlexPlayMetadata play, CancellationToken cancellationToken = default) =>
        RunAsync("predictive", ct => WarmPredictiveInnerAsync(play, ct), cancellationToken);

    private async Task<WarmResult> WarmPredictiveInnerAsync(PlexPlayMetadata play, CancellationToken ct)
    {
        if (play.Kind == "movie")
            return await WarmPlayedMovieAsync(play, ct).ConfigureAwait(false);
        return await WarmPlayedEpisodeAsync(play, ct).ConfigureAwait(false);
    }

    private async Task<WarmResult> WarmPlayedMovieAsync(PlexPlayMetadata play, CancellationToken ct)
    {
        int? tmdbId = await ResolveMovieIdAsync(play, ct).ConfigureAwait(false);
        if (tmdbId is null)
            return new WarmResult("predictive", ItemsWarmed: 0, ImagesWarmed: 0, Missing: 1, Errors: 0, Skipped: false, ElapsedSeconds: 0);

        int images = 0, movieItems = 0;
        foreach (string lang in _languages)
        {
            images += await WarmOneMovieAsync(tmdbId.Value, lang, ct).ConfigureAwait(false);
            movieItems++;
        }
        (int similarItems, int similarImages) = await WarmSimilarAsync(tmdbId.Value, isMovie: true, ct).ConfigureAwait(false);
        _logger.LogInformation("Predictive warm (movie): played tmdb {Id} + {Count} similar", tmdbId, similarItems);
        return new WarmResult("predictive", movieItems + similarItems, images + similarImages, Missing: 0, Errors: 0, Skipped: false, ElapsedSeconds: 0);
    }

    private async Task<WarmResult> WarmPlayedEpisodeAsync(PlexPlayMetadata play, CancellationToken ct)
    {
        int? showId = await ResolveShowIdAsync(play, ct).ConfigureAwait(false);
        if (showId is null)
            return new WarmResult("predictive", ItemsWarmed: 0, ImagesWarmed: 0, Missing: 1, Errors: 0, Skipped: false, ElapsedSeconds: 0);

        int totalItems = 0, totalImages = 0;
        foreach (string lang in _languages)
        {
            (int items, int images) = await WarmShowAroundAsync(showId.Value, play.Season, play.Episode, lang, ct).ConfigureAwait(false);
            totalItems += items;
            totalImages += images;
        }
        (int similarItems, int similarImages) = await WarmSimilarAsync(showId.Value, isMovie: false, ct).ConfigureAwait(false);
        _logger.LogInformation("Predictive warm (episode): show tmdb {Id} s{Season}e{Episode} = {Items} items + {Count} similar",
            showId, play.Season, play.Episode, totalItems, similarItems);
        return new WarmResult("predictive", totalItems + similarItems, totalImages + similarImages, Missing: 0, Errors: 0, Skipped: false, ElapsedSeconds: 0);
    }

    /// <summary>Resolves the played movie to a tmdb id: provider guid first, then title+year auto-match.</summary>
    private async Task<int?> ResolveMovieIdAsync(PlexPlayMetadata play, CancellationToken ct)
    {
        try
        {
            foreach (string guid in play.Guids)
            {
                GuidLookupResult? result = await _lookup.LookupAsync(guid, ct).ConfigureAwait(false);
                if (result?.Kind == "movie" && result.TmdbId is { } id)
                    return id;
            }
            if (play.Title is not null)
            {
                MetadataContainer container = await _movies.MatchAsync(
                    MatchHint.Empty with { Kind = MatchKind.Movie, Title = play.Title, Year = play.Year }, ct).ConfigureAwait(false);
                if (TmdbIdOf(container) is { } id)
                    return id;
            }
        }
        catch (TmdbNotFoundException)
        {
        }
        return null;
    }

    /// <summary>Resolves the played episode's SHOW to a tmdb id: show-level guid first, then show-title match.</summary>
    private async Task<int?> ResolveShowIdAsync(PlexPlayMetadata play, CancellationToken ct)
    {
        try
        {
            foreach (string guid in play.Guids)
            {
                GuidLookupResult? result = await _lookup.LookupAsync(guid, ct).ConfigureAwait(false);
                if (result?.Kind == "show" && result.TmdbId is { } id)
                    return id;
            }
            if (play.ShowTitle is not null)
            {
                MetadataContainer container = await _tv.MatchAsync(
                    MatchHint.Empty with { Kind = MatchKind.Show, Title = play.ShowTitle, Year = play.Year }, includeChildren: false, ct).ConfigureAwait(false);
                if (TmdbIdOf(container) is { } id)
                    return id;
            }
        }
        catch (TmdbNotFoundException)
        {
        }
        return null;
    }

    private static int? TmdbIdOf(MetadataContainer container)
    {
        if (container.Metadata.Count == 0)
            return null;
        if (!RatingKey.TryParse(container.Metadata[0].RatingKey, out ParsedRatingKey parsed) || parsed.Source != "tmdb")
            return null;
        return int.TryParse(parsed.Id, NumberStyles.None, CultureInfo.InvariantCulture, out int id) ? id : null;
    }

    /// <summary>
    /// Warms the played show's card, its season and the played episode + next episodes
    /// (the autoplay queue); a season-finale play primes the next season's first episodes.
    /// </summary>
    private async Task<(int Items, int Images)> WarmShowAroundAsync(int showId, int? season, int? episode, string lang, CancellationToken ct)
    {
        int items = 0, images = 0;
        TmdbShow show = await _tmdb.GetShowAsync(showId, lang, ct).ConfigureAwait(false);
        images += await WarmImageAsync(show.PosterPath, ct).ConfigureAwait(false)
            + await WarmImageAsync(show.BackdropPath, ct).ConfigureAwait(false);
        RecordItem("show", showId, "show", title: show.Name, year: YearOf(show.FirstAirDate), thumb: show.PosterPath, lang: lang);
        items++;

        int playedSeason = Math.Max(1, season ?? 1);
        int playedEpisode = Math.Max(1, episode ?? 1);

        TmdbSeason seasonData = await _tmdb.GetSeasonAsync(showId, playedSeason, lang, ct).ConfigureAwait(false);
        images += await WarmImageAsync(seasonData.PosterPath, ct).ConfigureAwait(false);
        RecordItem("season", seasonData.Id, "season", showId, title: show.Name, year: YearOf(show.FirstAirDate), thumb: seasonData.PosterPath, lang: lang);
        items++;

        int warmed = 0;
        foreach (TmdbEpisode e in seasonData.Episodes ?? [])
        {
            if (e.EpisodeNumber < playedEpisode || warmed >= NextEpisodesToWarm)
                continue;
            await WarmOneEpisodeAsync(showId, e.SeasonNumber, e.EpisodeNumber, show.Name, e.StillPath, lang, ct).ConfigureAwait(false);
            items++;
            warmed++;
        }

        // Season finale → prime the next season's opening, so the queue continues
        // across the boundary without paying upstream on the next autoplay.
        int lastInSeason = (seasonData.Episodes ?? []).Select(e => e.EpisodeNumber).DefaultIfEmpty(0).Max();
        int maxSeason = (show.Seasons ?? []).Select(s => s.SeasonNumber).DefaultIfEmpty(playedSeason).Max();
        if (playedEpisode >= lastInSeason && playedSeason < maxSeason)
        {
            TmdbSeason next = await _tmdb.GetSeasonAsync(showId, playedSeason + 1, lang, ct).ConfigureAwait(false);
            images += await WarmImageAsync(next.PosterPath, ct).ConfigureAwait(false);
            RecordItem("season", next.Id, "season", showId, title: show.Name, year: YearOf(show.FirstAirDate), thumb: next.PosterPath, lang: lang);
            items++;
            int primed = 0;
            foreach (TmdbEpisode e in next.Episodes ?? [])
            {
                if (primed >= NextSeasonPriming)
                    break;
                await WarmOneEpisodeAsync(showId, e.SeasonNumber, e.EpisodeNumber, show.Name, e.StillPath, lang, ct).ConfigureAwait(false);
                items++;
                primed++;
            }
        }
        return (items, images);
    }

    /// <summary>Warms one episode the dedicated endpoint Plex uses (plus its still and index row).</summary>
    private async Task WarmOneEpisodeAsync(int showId, int seasonNumber, int episodeNumber, string? showName, string? stillPath, string lang, CancellationToken ct)
    {
        TmdbEpisode episode = await _tmdb.GetEpisodeAsync(showId, seasonNumber, episodeNumber, lang, ct).ConfigureAwait(false);
        await WarmImageAsync(episode.StillPath, ct).ConfigureAwait(false);
        RecordItem("episode", episode.Id, "episode", showId, title: showName, year: YearOf(episode.AirDate), thumb: stillPath, lang: lang);
    }

    /// <summary>
    /// Warms the top <see cref="SimilarDepth"/> similar titles. Movies warm fully
    /// (details + artwork); shows warm as cards (metadata + artwork, no season crawl)
    /// so a play event stays bounded.
    /// </summary>
    private async Task<(int Items, int Images)> WarmSimilarAsync(int tmdbId, bool isMovie, CancellationToken ct)
    {
        int items = 0, images = 0;
        if (isMovie)
        {
            IReadOnlyList<TmdbMovieSummary> similar = await _tmdb.GetSimilarMoviesAsync(tmdbId, null, ct).ConfigureAwait(false);
            foreach (TmdbMovieSummary s in similar.Take(SimilarDepth))
            {
                foreach (string lang in _languages)
                    images += await WarmOneMovieAsync(s.Id, lang, ct).ConfigureAwait(false);
                items++;
            }
        }
        else
        {
            IReadOnlyList<TmdbShowSummary> similar = await _tmdb.GetSimilarShowsAsync(tmdbId, null, ct).ConfigureAwait(false);
            foreach (TmdbShowSummary s in similar.Take(SimilarDepth))
            {
                TmdbShow show = await _tmdb.GetShowAsync(s.Id, null, ct).ConfigureAwait(false);
                images += await WarmImageAsync(show.PosterPath, ct).ConfigureAwait(false)
                    + await WarmImageAsync(show.BackdropPath, ct).ConfigureAwait(false);
                RecordItem("show", s.Id, "show", title: show.Name, year: YearOf(show.FirstAirDate), thumb: show.PosterPath);
                items++;
            }
        }
        return (items, images);
    }

    // ---- internals ----

    private async Task<WarmResult> WarmMoviesInnerAsync(CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(_options.RadarrUrl))
            return WarmResult.SkippedRun("movies");

        var client = new ArrClient(_options.RadarrUrl, _options.RadarrApiKey, _upstream);
        IReadOnlyList<ArrMovie> movies = await client.GetMoviesAsync(ct).ConfigureAwait(false);
        _logger.LogInformation("Warming {Count} movies from Radarr", movies.Count);
        SetProgressTotal(movies.Count * _languages.Count);

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
                foreach (string lang in _languages)
                {
                    Interlocked.Add(ref images, await WarmOneMovieAsync(tmdbId, lang, token).ConfigureAwait(false));
                    Interlocked.Increment(ref items);
                    UpdateProgress(movie.Title);
                }
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
        SetProgressTotal(series.Count * _languages.Count);

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
                foreach (string lang in _languages)
                {
                    (bool found, int itemCount, int imageCount) = await WarmOneShowByTvdbAsync(tvdbId, lang, token).ConfigureAwait(false);
                    if (!found)
                    {
                        Interlocked.Increment(ref missing);
                        return;
                    }
                    Interlocked.Add(ref items, itemCount);
                    Interlocked.Add(ref images, imageCount);
                }
                UpdateProgress(entry.Title);
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
    private async Task<int> WarmOneMovieAsync(int tmdbId, string lang, CancellationToken ct)
    {
        await _movies.GetMovieMetadataAsync(
            tmdbId.ToString(CultureInfo.InvariantCulture), lang, null, ct).ConfigureAwait(false);
        TmdbMovie movie = await _tmdb.GetMovieAsync(tmdbId, lang, ct).ConfigureAwait(false);
        int images = await WarmImageAsync(movie.PosterPath, ct).ConfigureAwait(false)
            + await WarmImageAsync(movie.BackdropPath, ct).ConfigureAwait(false);
        RecordItem("movie", tmdbId, "movie", title: movie.Title, year: YearOf(movie.ReleaseDate), thumb: movie.PosterPath, lang: lang);
        return images;
    }

    /// <summary>Warms one show by tvdbId: show metadata + every season/episode + artwork.</summary>
    private async Task<(bool Found, int Items, int Images)> WarmOneShowByTvdbAsync(int tvdbId, string lang, CancellationToken ct)
    {
        IReadOnlyList<TmdbShowSummary> found =
            await _tmdb.FindTvByExternalIdAsync("tvdb_id", tvdbId.ToString(CultureInfo.InvariantCulture), lang, ct)
                .ConfigureAwait(false);
        if (found.Count == 0)
            return (Found: false, 0, 0);

        int showId = found[0].Id;
        await _tv.GetShowMetadataAsync(showId.ToString(CultureInfo.InvariantCulture),
            includeChildren: true, lang, null, ct).ConfigureAwait(false);

        TmdbShow show = await _tmdb.GetShowAsync(showId, lang, ct).ConfigureAwait(false);
        int images = await WarmImageAsync(show.PosterPath, ct).ConfigureAwait(false)
            + await WarmImageAsync(show.BackdropPath, ct).ConfigureAwait(false);
        RecordItem("show", showId, "show", title: show.Name, year: YearOf(show.FirstAirDate), thumb: show.PosterPath, lang: lang);
        int items = 1;

        foreach (TmdbSeasonSummary seasonSummary in show.Seasons ?? [])
        {
            TmdbSeason season = await _tmdb.GetSeasonAsync(showId, seasonSummary.SeasonNumber, lang, ct).ConfigureAwait(false);
            images += await WarmImageAsync(season.PosterPath, ct).ConfigureAwait(false);
            RecordItem("season", season.Id, "season", showId, title: show.Name, year: YearOf(show.FirstAirDate), thumb: season.PosterPath, lang: lang);
            items++;

            foreach (TmdbEpisode episode in season.Episodes ?? [])
            {
                await _tmdb.GetEpisodeAsync(showId, episode.SeasonNumber, episode.EpisodeNumber, lang, ct).ConfigureAwait(false);
                images += await WarmImageAsync(episode.StillPath, ct).ConfigureAwait(false);
                RecordItem("episode", episode.Id, "episode", showId,
                    title: show.Name, year: YearOf(episode.AirDate), thumb: episode.StillPath, lang: lang);
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
            _progress = new WarmProgress(source, TotalItems: 0, ProcessedItems: 0, ImagesWarmed: 0, Errors: 0, CurrentItem: null, StartedAt: started);
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
                _progress = null;
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

    private void SetProgressTotal(int total)
    {
        if (_progress is { } p)
            _progress = p with { TotalItems = total };
    }

    private void UpdateProgress(string? currentItem)
    {
        if (_progress is { } p)
            _progress = p with { ProcessedItems = p.ProcessedItems + 1, CurrentItem = currentItem };
    }

    private void RecordItem(string kind, int sourceId, string idKind, int? parentId = null,
        string? title = null, int? year = null, string? thumb = null, string lang = "en-US")
    {
        string id = parentId is null
            ? $"{idKind}-{sourceId.ToString(CultureInfo.InvariantCulture)}"
            : $"{idKind}-{parentId.Value.ToString(CultureInfo.InvariantCulture)}-{sourceId.ToString(CultureInfo.InvariantCulture)}";
        var now = DateTimeOffset.UtcNow;
        // The browse list (§21) serves /img/{hash}?width=… thumbs from this column; the
        // hash is the rewritten local path of the TMDB artwork path the warm already fetched.
        string? thumbLocal = thumb is null ? null : ImageCache.RewriteToLocalPath(_tmdb.ImageUrl(thumb)!);
        _items.Put(new CachedItem(
            Id: id,
            Kind: kind,
            Source: "tmdb",
            SourceId: sourceId.ToString(CultureInfo.InvariantCulture),
            Lang: lang,
            Json: "{}",
            FetchedAt: now,
            ExpiresAt: now.AddDays(1),
            ETag: null,
            Title: title,
            Year: year,
            Thumb: thumbLocal));
    }

    /// <summary>Extracts the year from a TMDB "YYYY-MM-DD" date string, or null.</summary>
    private static int? YearOf(string? date)
    {
        if (date is null || date.Length < 4)
            return null;
        return int.TryParse(date.AsSpan(0, 4), NumberStyles.None, CultureInfo.InvariantCulture, out int year)
            ? year
            : null;
    }
}
