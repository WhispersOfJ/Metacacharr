using System.Globalization;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Metacache.Core;
using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Core.Providers;
using Metacache.Plex.Mappers;
using Metacache.Plex.Models;

namespace Metacache.Plex;

/// <summary>
/// TV half of the provider logic (DESIGN.md §15.7): show/season/episode matching
/// through the pure <see cref="MatchScorer"/> (structure-gated on season/episode
/// indices or air date), full show/season/episode metadata, and the paged
/// /children + /grandchildren hierarchy endpoints.
/// </summary>
public sealed class TvProviderService
{
    private const int ManualShowEnrichDepth = 8;

    private readonly TmdbClient _tmdb;
    private readonly TvdbClient _tvdb;
    private readonly TmdbOptions _options;
    private readonly MatchPolicy _policy;
    private readonly ImageCache _images;
    private readonly ILogger<TvProviderService> _logger;

    public TvProviderService(
        TmdbClient tmdb, TvdbClient tvdb, TmdbOptions options, MatchPolicy policy, ImageCache images,
        ILogger<TvProviderService> logger)
    {
        _tmdb = tmdb;
        _tvdb = tvdb;
        _options = options;
        _policy = policy;
        _images = images;
        _logger = logger;
    }

    // ---- match ----

    /// <summary>
    /// Resolves a pinned override target (a tmdb-source rating key, §15.10) into a single
    /// match-shaped container, or null when the key is not a tmdb-sourced show/season/
    /// episode key or the target no longer resolves upstream.
    /// </summary>
    public async Task<MetadataContainer?> MatchOverrideAsync(
        string ratingKey, bool includeChildren, string? language, CancellationToken cancellationToken)
    {
        if (!RatingKey.TryParse(ratingKey, out ParsedRatingKey parsed) || parsed.Source != "tmdb")
            return null;
        if (!int.TryParse(parsed.Id, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        switch (parsed.Kind)
        {
            case "show":
                {
                    TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
                    RegisterShowImages(show);
                    MetadataItem item = TvMapper.ToMatchShow(show, ProviderIdentities.Tv, _options.ImageBaseUrl, language);
                    if (includeChildren)
                        item = item with { Children = SeasonChildren(show) };
                    return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1, [item]);
                }
            case "season" when parsed.Indices.Length == 1:
                {
                    TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
                    RegisterShowImages(show);
                    TmdbSeasonSummary? summary = (show.Seasons ?? []).FirstOrDefault(s => s.SeasonNumber == parsed.Indices[0]);
                    if (summary is null)
                        return null;
                    MetadataItem item = TvMapper.ToSeasonItem(show, summary, ProviderIdentities.Tv, _options.ImageBaseUrl);
                    if (includeChildren)
                    {
                        TmdbSeason season = await _tmdb.GetSeasonAsync(show.Id, parsed.Indices[0], language, cancellationToken);
                        item = item with { Children = EpisodeChildren(season, show) };
                    }
                    return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1, [item]);
                }
            case "episode" when parsed.Indices.Length == 2:
                {
                    TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
                    RegisterShowImages(show);
                    var hint = MatchHint.Empty with
                    {
                        Kind = MatchKind.Episode,
                        Language = language,
                        ParentIndex = parsed.Indices[0]
                    };
                    IReadOnlyList<TmdbEpisode> episodes = await GetEpisodesAsync(show, hint, cancellationToken);
                    TmdbEpisode? episode = episodes.FirstOrDefault(e =>
                        e.SeasonNumber == parsed.Indices[0] && e.EpisodeNumber == parsed.Indices[1]);
                    if (episode is null)
                        return null;
                    return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1,
                        [TvMapper.ToEpisodeItem(episode, show, ProviderIdentities.Tv, _options.ImageBaseUrl)]);
                }
            default:
                return null;
        }
    }

    public async Task<MetadataContainer> MatchAsync(MatchHint hint, bool includeChildren, CancellationToken cancellationToken) =>
        hint.Kind switch
        {
            MatchKind.Season => await MatchSeasonAsync(hint, includeChildren, cancellationToken),
            MatchKind.Episode => await MatchEpisodeAsync(hint, cancellationToken),
            _ => await MatchShowAsync(hint, includeChildren, cancellationToken)
        };

    private async Task<MetadataContainer> MatchShowAsync(MatchHint hint, bool includeChildren, CancellationToken ct)
    {
        IReadOnlyList<TmdbShowSummary> summaries = await ResolveShowSummariesAsync(hint, ct);
        if (summaries.Count == 0)
            return Empty();

        IReadOnlyList<MatchCandidate> candidates = await CandidatesForAsync(summaries, hint, ct);
        IReadOnlyList<ScoredMatch> scored = MatchScorer.Score(hint, candidates, _policy);

        if (hint.Manual)
        {
            TmdbShow[] shows = await Task.WhenAll(scored
                .Take(ManualShowEnrichDepth)
                .Select(s => _tmdb.GetShowAsync(IdOf(s.Candidate.Id), hint.Language, ct)));
            foreach (TmdbShow enriched in shows)
                RegisterShowImages(enriched);
            var items = shows
                .Select(s => TvMapper.ToMatchShow(s, ProviderIdentities.Tv, _options.ImageBaseUrl, hint.Language))
                .ToList();
            return new MetadataContainer(0, items.Count, ProviderIdentities.Tv, items.Count, items);
        }

        ScoredMatch? best = scored.FirstOrDefault();
        if (best is null)
            return Empty();

        TmdbShow show = await _tmdb.GetShowAsync(IdOf(best.Candidate.Id), hint.Language, ct);
        RegisterShowImages(show);
        MetadataItem item = TvMapper.ToMatchShow(show, ProviderIdentities.Tv, _options.ImageBaseUrl, hint.Language);
        if (includeChildren)
            item = item with { Children = SeasonChildren(show) };
        _logger.LogInformation("Auto-matched show '{Title}' → tmdb {Id} (score {Score:F2})", hint.Title, show.Id, best.Score);
        return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1, [item]);
    }

    private async Task<MetadataContainer> MatchSeasonAsync(MatchHint hint, bool includeChildren, CancellationToken ct)
    {
        TmdbShow? show = await ResolveShowAsync(hint, ct);
        if (show is null || show.Seasons is null || show.Seasons.Count == 0)
            return Empty();

        IReadOnlyList<MatchCandidate> candidates = show.Seasons.Select(s => CandidateFromSeason(show, s)).ToList();
        IReadOnlyList<ScoredMatch> scored = MatchScorer.Score(hint, candidates, _policy);

        if (hint.Manual)
        {
            var items = new List<MetadataItem>();
            foreach (ScoredMatch result in scored)
            {
                TmdbSeasonSummary? summary = show.Seasons.FirstOrDefault(s =>
                    s.SeasonNumber == ParseStructureId(result.Candidate.Id).Season);
                if (summary is not null)
                    items.Add(TvMapper.ToSeasonItem(show, summary, ProviderIdentities.Tv, _options.ImageBaseUrl));
            }
            return new MetadataContainer(0, items.Count, ProviderIdentities.Tv, items.Count, items);
        }

        ScoredMatch? best = scored.FirstOrDefault();
        if (best is null)
            return Empty();

        int seasonNumber = ParseStructureId(best.Candidate.Id).Season;
        MetadataItem item = TvMapper.ToSeasonItem(show,
            show.Seasons.First(s => s.SeasonNumber == seasonNumber),
            ProviderIdentities.Tv, _options.ImageBaseUrl);
        if (includeChildren)
        {
            TmdbSeason season = await _tmdb.GetSeasonAsync(show.Id, seasonNumber, hint.Language, ct);
            item = item with { Children = EpisodeChildren(season, show) };
        }
        _logger.LogInformation("Auto-matched season '{Show}' S{Season} (score {Score:F2})",
            NameOf(show), seasonNumber, best.Score);
        return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1, [item]);
    }

    private async Task<MetadataContainer> MatchEpisodeAsync(MatchHint hint, CancellationToken ct)
    {
        TmdbShow? show = await ResolveShowAsync(hint, ct);
        if (show is null)
            return Empty();

        IReadOnlyList<TmdbEpisode> episodes = await GetEpisodesAsync(show, hint, ct);
        if (episodes.Count == 0)
            return Empty();

        IReadOnlyList<MatchCandidate> candidates = episodes.Select(e => CandidateFromEpisode(e, show)).ToList();
        IReadOnlyList<ScoredMatch> scored = MatchScorer.Score(hint, candidates, _policy);

        if (hint.Manual)
        {
            var items = new List<MetadataItem>();
            foreach (ScoredMatch result in scored)
            {
                (int season, int episode) = ParseStructureId(result.Candidate.Id);
                TmdbEpisode? match = episodes.FirstOrDefault(e => e.SeasonNumber == season && e.EpisodeNumber == episode);
                if (match is not null)
                    items.Add(TvMapper.ToEpisodeItem(match, show, ProviderIdentities.Tv, _options.ImageBaseUrl));
            }
            return new MetadataContainer(0, items.Count, ProviderIdentities.Tv, items.Count, items);
        }

        ScoredMatch? best = scored.FirstOrDefault();
        if (best is null)
            return Empty();

        (int seasonNumber, int episodeNumber) = ParseStructureId(best.Candidate.Id);
        _logger.LogInformation("Auto-matched episode '{Show}' S{Season}E{Episode} (score {Score:F2})",
            NameOf(show), seasonNumber, episodeNumber, best.Score);
        return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1,
            [TvMapper.ToEpisodeItem(episodes.First(e => e.SeasonNumber == seasonNumber && e.EpisodeNumber == episodeNumber),
                show, ProviderIdentities.Tv, _options.ImageBaseUrl)]);
    }

    /// <summary>
    /// Resolves the show a season/episode match targets: an external guid pins it
    /// directly; otherwise the (grand)parentTitle is searched and scored, requiring
    /// the auto threshold for auto-matches (a wrong show must never commit).
    /// </summary>
    private async Task<TmdbShow?> ResolveShowAsync(MatchHint hint, CancellationToken ct)
    {
        if (hint.ExternalGuids.Count > 0)
        {
            foreach (string guid in hint.ExternalGuids)
            {
                if (!ExternalGuid.TryParse(guid, out string source, out string id))
                    continue;
                if (source == "tmdb" && int.TryParse(id, NumberStyles.None, CultureInfo.InvariantCulture, out int showId))
                    return await _tmdb.GetShowAsync(showId, hint.Language, ct);
                if (source is "imdb" or "tvdb")
                {
                    IReadOnlyList<TmdbShowSummary> found = await _tmdb
                        .FindTvByExternalIdAsync(source == "imdb" ? "imdb_id" : "tvdb_id", id, hint.Language, ct);
                    if (found.Count > 0)
                        return await _tmdb.GetShowAsync(found[0].Id, hint.Language, ct);
                }
            }
            return null;
        }

        string? showTitle = hint.ParentTitle ?? hint.GrandparentTitle;
        if (string.IsNullOrWhiteSpace(showTitle))
            return null;

        IReadOnlyList<TmdbShowSummary> search = await _tmdb.SearchShowsAsync(showTitle, hint.Year, hint.Language, ct);
        if (search.Count == 0)
            return null;

        var showHint = hint with { Title = showTitle, Kind = MatchKind.Show, ParentTitle = null, GrandparentTitle = null };
        IReadOnlyList<ScoredMatch> scored = MatchScorer.Score(showHint, search.Select(CandidateFromSummary).ToList(), _policy);
        ScoredMatch? best = scored.FirstOrDefault();
        if (best is null)
            return null;

        return await _tmdb.GetShowAsync(IdOf(best.Candidate.Id), hint.Language, ct);
    }

    /// <summary>Show candidates for a show match (guid pin or search).</summary>
    private async Task<IReadOnlyList<TmdbShowSummary>> ResolveShowSummariesAsync(MatchHint hint, CancellationToken ct)
    {
        if (hint.ExternalGuids.Count > 0)
        {
            foreach (string guid in hint.ExternalGuids)
            {
                if (!ExternalGuid.TryParse(guid, out string source, out string id))
                    continue;
                if (source == "tmdb" && int.TryParse(id, NumberStyles.None, CultureInfo.InvariantCulture, out int showId))
                {
                    TmdbShow show = await _tmdb.GetShowAsync(showId, hint.Language, ct);
                    return [FromShow(show)];
                }
                if (source is "imdb" or "tvdb")
                {
                    IReadOnlyList<TmdbShowSummary> found = await _tmdb
                        .FindTvByExternalIdAsync(source == "imdb" ? "imdb_id" : "tvdb_id", id, hint.Language, ct);
                    if (found.Count > 0)
                    {
                        TmdbShow show = await _tmdb.GetShowAsync(found[0].Id, hint.Language, ct);
                        return [FromShow(show)];
                    }
                }
            }
            return [];
        }

        if (string.IsNullOrWhiteSpace(hint.Title))
            return [];
        return await _tmdb.SearchShowsAsync(hint.Title, hint.Year, hint.Language, ct);
    }

    /// <summary>
    /// Episodes for a season/episode match: just the hinted season, or all seasons when
    /// only an air date / manual search is given. When TMDB has the show but no episode
    /// data at all, augments from TVDB (§15.9) so index/air-date matching still works.
    /// </summary>
    private async Task<IReadOnlyList<TmdbEpisode>> GetEpisodesAsync(TmdbShow show, MatchHint hint, CancellationToken ct)
    {
        IReadOnlyList<int> seasonNumbers = (show.Seasons ?? []).Select(s => s.SeasonNumber).ToList();
        if (hint.ParentIndex is { } only)
        {
            if (!seasonNumbers.Contains(only))
                return [];
            TmdbSeason season = await _tmdb.GetSeasonAsync(show.Id, only, hint.Language, ct);
            IReadOnlyList<TmdbEpisode> seasonEpisodes = season.Episodes ?? [];
            return seasonEpisodes.Count > 0 ? seasonEpisodes : await TvdbEpisodesOrEmptyAsync(show.Id, ct);
        }

        TmdbSeason[] seasons = await Task.WhenAll(seasonNumbers.Select(n => _tmdb.GetSeasonAsync(show.Id, n, hint.Language, ct)));
        IReadOnlyList<TmdbEpisode> episodes = seasons.SelectMany(s => s.Episodes ?? []).ToList();
        return episodes.Count > 0 ? episodes : await TvdbEpisodesOrEmptyAsync(show.Id, ct);
    }

    /// <summary>All episodes from TVDB via the show's tvdb external id, or empty when TVDB has none either.</summary>
    private async Task<IReadOnlyList<TmdbEpisode>> TvdbEpisodesOrEmptyAsync(int tmdbShowId, CancellationToken ct)
    {
        try
        {
            TmdbExternalIds ids = await _tmdb.GetShowExternalIdsAsync(tmdbShowId, ct);
            if (ids.TvdbId is not { } tvdbId)
                return [];
            TvdbSeriesEpisodes? series = await _tvdb.GetSeriesEpisodesAsync(tvdbId, ct);
            return (series?.Episodes ?? []).Select(TvdbMapper.ToTmdbEpisode).ToList();
        }
        catch (TmdbNotFoundException)
        {
            return [];
        }
    }

    // ---- metadata ----

    public async Task<MetadataContainer?> GetShowMetadataAsync(
        string showId, bool includeChildren, string? language, string? country, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
        RegisterShowImages(show);

        Task<TmdbCredits> creditsTask = _tmdb.GetShowCreditsAsync(id, language, cancellationToken);
        Task<TmdbContentRatingsResponse> ratingsTask = _tmdb.GetContentRatingsAsync(id, cancellationToken);
        Task<TmdbExternalIds> extTask = _tmdb.GetShowExternalIdsAsync(id, cancellationToken);
        await Task.WhenAll(creditsTask, ratingsTask, extTask);
        TmdbCredits credits = await creditsTask;
        TmdbContentRatingsResponse ratings = await ratingsTask;
        TmdbExternalIds externalIds = await extTask;
        RegisterCredits(credits);

        MetadataItem item = TvMapper.ToShow(show, credits, ratings, externalIds, country, language,
            ProviderIdentities.Tv, _options.ImageBaseUrl, includeChildren ? SeasonItems(show) : null);
        return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1, [item]);
    }

    public async Task<MetadataContainer?> GetSeasonMetadataAsync(
        string showId, int seasonNumber, bool includeChildren, string? language, string? country, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
        TmdbSeason season = await _tmdb.GetSeasonAsync(id, seasonNumber, language, cancellationToken);
        RegisterShowImages(show);
        RegisterSeasonImages(season);
        TmdbContentRatingsResponse ratings = await _tmdb.GetContentRatingsAsync(id, cancellationToken);

        MetadataItem item = TvMapper.ToSeason(show, season, ratings, country, ProviderIdentities.Tv, _options.ImageBaseUrl,
            includeChildren ? EpisodeItems(season, show) : null);
        return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1, [item]);
    }

    public async Task<MetadataContainer?> GetEpisodeMetadataAsync(
        string showId, int seasonNumber, int episodeNumber, string? language, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbEpisode episode;
        string? tvdbStillLocal = null;
        string? tvdbEpisodeGuid = null;
        try
        {
            episode = await _tmdb.GetEpisodeAsync(id, seasonNumber, episodeNumber, language, cancellationToken);
        }
        catch (TmdbNotFoundException)
        {
            // TMDB lacks the episode (obscure shows often have the series but no episode
            // rows) — fall back to TVDB via the show's tvdb external id (§15.9).
            TvdbEpisode? tvdb = await TryGetTvdbEpisodeAsync(id, seasonNumber, episodeNumber, cancellationToken);
            if (tvdb is null)
                throw; // rethrow keeps the 404 response
            episode = TvdbMapper.ToTmdbEpisode(tvdb);
            if (!string.IsNullOrEmpty(tvdb.Image))
                _images.RegisterUrl(tvdb.Image);
            tvdbStillLocal = tvdb.Image is null ? null : ImageCache.RewriteToLocalPath(tvdb.Image);
            tvdbEpisodeGuid = $"tvdb://{tvdb.Id}";
        }

        TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
        RegisterShowImages(show);
        if (_tmdb.ImageUrl(episode.StillPath) is { } still)
            _images.RegisterUrl(still);

        MetadataItem item = TvMapper.ToEpisodeItem(episode, show, ProviderIdentities.Tv, _options.ImageBaseUrl);
        if (tvdbStillLocal is not null)
            item = item with { Thumb = tvdbStillLocal };
        if (tvdbEpisodeGuid is not null)
            item = item with { GuidItems = [new GuidItem(tvdbEpisodeGuid)] };
        return new MetadataContainer(0, 1, ProviderIdentities.Tv, 1, [item]);
    }

    /// <summary>The TVDB episode at the given structure position, or null when TVDB lacks it too.</summary>
    private async Task<TvdbEpisode?> TryGetTvdbEpisodeAsync(
        int tmdbShowId, int seasonNumber, int episodeNumber, CancellationToken ct)
    {
        try
        {
            TmdbExternalIds ids = await _tmdb.GetShowExternalIdsAsync(tmdbShowId, ct);
            if (ids.TvdbId is not { } tvdbId)
                return null;
            TvdbSeriesEpisodes? series = await _tvdb.GetSeriesEpisodesAsync(tvdbId, ct);
            return (series?.Episodes ?? []).FirstOrDefault(e => e.SeasonNumber == seasonNumber && e.Number == episodeNumber);
        }
        catch (TmdbNotFoundException)
        {
            return null;
        }
    }

    // ---- children / grandchildren (paged) ----

    public async Task<MetadataContainer?> GetShowChildrenAsync(
        string showId, string? language, HttpRequest request, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
        RegisterShowImages(show);
        return Page(request, SeasonItems(show));
    }

    public async Task<MetadataContainer?> GetShowGrandchildrenAsync(
        string showId, string? language, HttpRequest request, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
        RegisterShowImages(show);
        IReadOnlyList<TmdbEpisode> episodes = await GetEpisodesAsync(show, MatchHint.Empty with { Kind = MatchKind.Episode }, cancellationToken);
        var items = episodes
            .Select(e => TvMapper.ToEpisodeItem(e, show, ProviderIdentities.Tv, _options.ImageBaseUrl))
            .ToList();
        return Page(request, items);
    }

    public async Task<MetadataContainer?> GetSeasonChildrenAsync(
        string showId, int seasonNumber, string? language, HttpRequest request, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
        TmdbSeason season = await _tmdb.GetSeasonAsync(id, seasonNumber, language, cancellationToken);
        RegisterShowImages(show);
        RegisterSeasonImages(season);
        var items = (season.Episodes ?? [])
            .Select(e => TvMapper.ToEpisodeItem(e, show, ProviderIdentities.Tv, _options.ImageBaseUrl))
            .ToList();
        return Page(request, items);
    }

    // ---- images ----

    public async Task<ImageContainer?> GetShowImagesAsync(string showId, string? language, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
        RegisterShowImages(show);
        var images = BuildImages(
            coverPoster: Local(_tmdb.ImageUrl(show.PosterPath)),
            background: Local(_tmdb.ImageUrl(show.BackdropPath)),
            show);
        return new ImageContainer(0, images.Count, ProviderIdentities.Tv, images.Count, images);
    }

    public async Task<ImageContainer?> GetSeasonImagesAsync(
        string showId, int seasonNumber, string? language, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbShow show = await _tmdb.GetShowAsync(id, language, cancellationToken);
        TmdbSeason season = await _tmdb.GetSeasonAsync(id, seasonNumber, language, cancellationToken);
        RegisterShowImages(show);
        RegisterSeasonImages(season);
        var images = BuildImages(
            coverPoster: Local(_tmdb.ImageUrl(season.PosterPath) ?? _tmdb.ImageUrl(show.PosterPath)),
            background: Local(_tmdb.ImageUrl(show.BackdropPath)),
            show);
        return new ImageContainer(0, images.Count, ProviderIdentities.Tv, images.Count, images);
    }

    public async Task<ImageContainer?> GetEpisodeImagesAsync(
        string showId, int seasonNumber, int episodeNumber, string? language, CancellationToken cancellationToken)
    {
        if (!int.TryParse(showId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbEpisode episode = await _tmdb.GetEpisodeAsync(id, seasonNumber, episodeNumber, language, cancellationToken);
        string? stillUrl = _tmdb.ImageUrl(episode.StillPath);
        if (stillUrl is not null)
            _images.RegisterUrl(stillUrl);
        string? still = Local(stillUrl);
        IReadOnlyList<ImageAsset> images = still is null
            ? []
            : [new ImageAsset("snapshot", still, episode.Name ?? "")];
        return new ImageContainer(0, images.Count, ProviderIdentities.Tv, images.Count, images);
    }

    // ---- helpers ----

    private MetadataContainer Page(HttpRequest request, IReadOnlyList<MetadataItem> items)
    {
        var (page, total, offset) = PlexPaging.Page(request, items);
        return new MetadataContainer(offset, total, ProviderIdentities.Tv, page.Count, page);
    }

    private ChildrenObject SeasonChildren(TmdbShow show) => new(SeasonItems(show).Count, SeasonItems(show));

    private IReadOnlyList<MetadataItem> SeasonItems(TmdbShow show) =>
        (show.Seasons ?? [])
            .Select(s => TvMapper.ToSeasonItem(show, s, ProviderIdentities.Tv, _options.ImageBaseUrl))
            .ToList();

    private IReadOnlyList<MetadataItem> EpisodeItems(TmdbSeason season, TmdbShow show) =>
        (season.Episodes ?? [])
            .Select(e => TvMapper.ToEpisodeItem(e, show, ProviderIdentities.Tv, _options.ImageBaseUrl))
            .ToList();

    private ChildrenObject EpisodeChildren(TmdbSeason season, TmdbShow show)
    {
        var items = EpisodeItems(season, show);
        return new ChildrenObject(items.Count, items);
    }

    private static IReadOnlyList<ImageAsset> BuildImages(string? coverPoster, string? background, TmdbShow show)
    {
        var images = new List<ImageAsset>();
        if (coverPoster is not null)
            images.Add(new ImageAsset("coverPoster", coverPoster, NameOf(show)));
        if (background is not null)
            images.Add(new ImageAsset("background", background, NameOf(show)));
        return images;
    }

    private static MetadataContainer Empty() =>
        new(0, 0, ProviderIdentities.Tv, 0, []);

    private static string NameOf(TmdbShow show) =>
        string.IsNullOrEmpty(show.Name) ? show.OriginalName ?? string.Empty : show.Name;

    private static MatchCandidate CandidateFromSummary(TmdbShowSummary summary) => new(
        Id: summary.Id.ToString(CultureInfo.InvariantCulture),
        Title: string.IsNullOrEmpty(summary.Name) ? summary.OriginalName ?? string.Empty : summary.Name,
        OriginalTitle: summary.OriginalName,
        Year: YearOf(summary.FirstAirDate),
        OriginalLanguage: summary.OriginalLanguage,
        Popularity: summary.Popularity,
        Adult: summary.Adult,
        ExternalIds: [$"tmdb://{summary.Id}"]);

    private static MatchCandidate CandidateFromSeason(TmdbShow show, TmdbSeasonSummary season) => new(
        Id: $"{season.SeasonNumber}",
        Title: string.IsNullOrEmpty(season.Name) ? $"Season {season.SeasonNumber}" : season.Name,
        OriginalTitle: null,
        Year: YearOf(season.AirDate) ?? YearOf(show.FirstAirDate),
        OriginalLanguage: show.OriginalLanguage,
        Popularity: show.Popularity,
        Adult: show.Adult,
        ExternalIds: [],
        ParentTitle: NameOf(show),
        Index: season.SeasonNumber);

    private static MatchCandidate CandidateFromEpisode(TmdbEpisode episode, TmdbShow show) => new(
        Id: $"{episode.SeasonNumber}-{episode.EpisodeNumber}",
        Title: string.IsNullOrEmpty(episode.Name) ? $"Episode {episode.EpisodeNumber}" : episode.Name,
        OriginalTitle: null,
        Year: YearOf(episode.AirDate) ?? YearOf(show.FirstAirDate),
        OriginalLanguage: show.OriginalLanguage,
        Popularity: show.Popularity,
        Adult: show.Adult,
        ExternalIds: [],
        ParentTitle: NameOf(show),
        Index: episode.EpisodeNumber,
        ParentIndex: episode.SeasonNumber,
        AirDate: episode.AirDate);

    private static TmdbShowSummary FromShow(TmdbShow show) => new(
        show.Id, show.Name, show.OriginalName, show.FirstAirDate, show.Overview, show.PosterPath,
        show.BackdropPath, show.Popularity, show.Adult, show.OriginalLanguage, show.VoteAverage);

    /// <summary>
    /// Builds match candidates, enriching guid-pinned shows with their real external
    /// ids (imdb/tvdb) so the scorer's exact-GUID override fires and the pinned item
    /// cannot be filtered out by the auto threshold (mirrors the movie flow).
    /// </summary>
    private async Task<IReadOnlyList<MatchCandidate>> CandidatesForAsync(
        IReadOnlyList<TmdbShowSummary> summaries, MatchHint hint, CancellationToken ct)
    {
        var candidates = summaries.Select(CandidateFromSummary).ToList();
        if (hint.ExternalGuids.Count == 0)
            return candidates;

        var enriched = new List<MatchCandidate>(candidates.Count);
        foreach (MatchCandidate candidate in candidates)
        {
            if (!int.TryParse(candidate.Id, NumberStyles.None, CultureInfo.InvariantCulture, out int showId))
            {
                enriched.Add(candidate);
                continue;
            }
            TmdbExternalIds ids = await _tmdb.GetShowExternalIdsAsync(showId, ct);
            enriched.Add(candidate with { ExternalIds = ExternalIdsOf(showId, ids) });
        }
        return enriched;
    }

    private static IReadOnlyList<string> ExternalIdsOf(int showId, TmdbExternalIds ids)
    {
        var list = new List<string> { $"tmdb://{showId}" };
        if (!string.IsNullOrEmpty(ids.ImdbId))
            list.Add($"imdb://{ids.ImdbId}");
        if (ids.TvdbId is { } tvdbId)
            list.Add($"tvdb://{tvdbId}");
        return list;
    }

    private static (int Season, int Episode) ParseStructureId(string id)
    {
        string[] parts = id.Split('-');
        return parts.Length == 2 && int.TryParse(parts[0], out int season) && int.TryParse(parts[1], out int episode)
            ? (season, episode)
            : (int.TryParse(id, out season) ? (season, 0) : (0, 0));
    }

    private static int IdOf(string id) => int.Parse(id, CultureInfo.InvariantCulture);

    private static int? YearOf(string? date)
    {
        if (date is null || date.Length < 4)
            return null;
        return int.TryParse(date.AsSpan(0, 4), NumberStyles.None, CultureInfo.InvariantCulture, out int year)
            ? year
            : null;
    }

    private static string? Local(string? url) =>
        url is null ? null : ImageCache.RewriteToLocalPath(url);

    private void RegisterShowImages(TmdbShow show)
    {
        if (_tmdb.ImageUrl(show.PosterPath) is { } poster)
            _images.RegisterUrl(poster);
        if (_tmdb.ImageUrl(show.BackdropPath) is { } backdrop)
            _images.RegisterUrl(backdrop);
    }

    private void RegisterSeasonImages(TmdbSeason season)
    {
        if (_tmdb.ImageUrl(season.PosterPath) is { } poster)
            _images.RegisterUrl(poster);
    }

    private void RegisterCredits(TmdbCredits credits)
    {
        foreach (TmdbCreditPerson person in (credits.Cast ?? []).Concat(credits.Crew ?? []))
        {
            if (_tmdb.ImageUrl(person.ProfilePath) is { } url)
                _images.RegisterUrl(url);
        }
    }
}
