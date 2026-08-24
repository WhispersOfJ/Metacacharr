using System.Globalization;
using Metacache.Core.Cache;
using Metacache.Core.Providers;
using Metacache.Plex.Models;

namespace Metacache.Plex.Mappers;

/// <summary>
/// Maps TMDB TV data onto Plex's provider schema (Metadata.md show/season/episode
/// shapes). Rating keys follow DESIGN.md §5: tmdb-show-{id}, tmdb-season-{id}-{n},
/// tmdb-episode-{id}-{s}-{e}; every item carries parent/grandparent keys so Plex can
/// rebuild the hierarchy. Artwork is rewritten to the local /img endpoint.
/// </summary>
public static class TvMapper
{
    // ---- show ----

    /// <summary>Compact show item for match responses.</summary>
    public static MetadataItem ToMatchShow(TmdbShow show, string providerIdentifier, string imageBaseUrl, string? language)
    {
        string ratingKey = RatingKey.Show("tmdb", show.Id.ToString(CultureInfo.InvariantCulture));
        return new MetadataItem(
            RatingKey: ratingKey,
            Key: $"/library/metadata/{ratingKey}",
            Guid: PlexGuid.Format(providerIdentifier, "show", ratingKey),
            Type: "show",
            Title: NameOf(show),
            OriginallyAvailableAt: DateOrNull(show.FirstAirDate),
            Thumb: Rewrite(show.PosterPath, imageBaseUrl),
            Year: YearOf(show.FirstAirDate));
    }

    /// <summary>Full show metadata (credits, ratings, external ids, optional season Children).</summary>
    public static MetadataItem ToShow(
        TmdbShow show,
        TmdbCredits? credits,
        TmdbContentRatingsResponse? ratings,
        TmdbExternalIds? externalIds,
        string? country,
        string? language,
        string providerIdentifier,
        string imageBaseUrl,
        IReadOnlyList<MetadataItem>? children = null)
    {
        string ratingKey = RatingKey.Show("tmdb", show.Id.ToString(CultureInfo.InvariantCulture));
        bool localized = IsLocalizedRequest(language, show.OriginalLanguage);

        return new MetadataItem(
            RatingKey: ratingKey,
            Key: $"/library/metadata/{ratingKey}",
            Guid: PlexGuid.Format(providerIdentifier, "show", ratingKey),
            Type: "show",
            Title: NameOf(show),
            OriginallyAvailableAt: DateOrNull(show.FirstAirDate),
            Thumb: Rewrite(show.PosterPath, imageBaseUrl),
            Art: Rewrite(show.BackdropPath, imageBaseUrl),
            OriginalTitle: localized ? show.OriginalName : null,
            Year: YearOf(show.FirstAirDate),
            Summary: show.Overview,
            Duration: show.EpisodeRunTime?.FirstOrDefault() is { } minutes ? minutes * 60_000 : null,
            ContentRating: PeopleMapper.TvContentRating(ratings, country),
            Genre: show.Genres is null ? null : show.Genres.Select(g => new GenreItem(g.Name ?? "")).ToList(),
            GuidItems: BuildShowGuids(show, externalIds),
            Role: PeopleMapper.ToRoles(credits, imageBaseUrl),
            Country: show.ProductionCountries is null ? null
                : show.ProductionCountries.Select(c => new CountryItem(c.Name ?? "")).ToList(),
            StudioItems: show.ProductionCompanies is null ? null
                : show.ProductionCompanies.Select(c => new StudioItem(c.Name ?? "")).ToList(),
            Network: show.Networks is null ? null
                : show.Networks.Select(n => new NetworkItem(n.Name ?? "")).ToList(),
            Children: children is null ? null : new ChildrenObject(children.Count, children));
    }

    // ---- season ----

    /// <summary>Season item from the show's seasons array (no episode list) — used for show children and season matches.</summary>
    public static MetadataItem ToSeasonItem(TmdbShow show, TmdbSeasonSummary season, string providerIdentifier, string imageBaseUrl)
    {
        string showKey = RatingKey.Show("tmdb", show.Id.ToString(CultureInfo.InvariantCulture));
        string ratingKey = RatingKey.Season("tmdb", show.Id.ToString(CultureInfo.InvariantCulture), season.SeasonNumber);
        return new MetadataItem(
            RatingKey: ratingKey,
            Key: $"/library/metadata/{ratingKey}",
            Guid: PlexGuid.Format(providerIdentifier, "season", ratingKey),
            Type: "season",
            Title: SeasonTitle(season),
            OriginallyAvailableAt: DateOrNull(season.AirDate),
            Thumb: Rewrite(season.PosterPath, imageBaseUrl) ?? Rewrite(show.PosterPath, imageBaseUrl),
            Art: Rewrite(show.BackdropPath, imageBaseUrl),
            Year: YearOf(season.AirDate) ?? YearOf(show.FirstAirDate),
            Index: season.SeasonNumber,
            ParentRatingKey: showKey,
            ParentKey: $"/library/metadata/{showKey}",
            ParentGuid: PlexGuid.Format(providerIdentifier, "show", showKey),
            ParentType: "show",
            ParentTitle: NameOf(show),
            ParentThumb: Rewrite(show.PosterPath, imageBaseUrl),
            ParentArt: Rewrite(show.BackdropPath, imageBaseUrl));
    }

    /// <summary>Full season metadata (content rating, summary, optional episode Children).</summary>
    public static MetadataItem ToSeason(
        TmdbShow show,
        TmdbSeason season,
        TmdbContentRatingsResponse? ratings,
        string? country,
        string providerIdentifier,
        string imageBaseUrl,
        IReadOnlyList<MetadataItem>? children = null)
    {
        string showKey = RatingKey.Show("tmdb", show.Id.ToString(CultureInfo.InvariantCulture));
        string ratingKey = RatingKey.Season("tmdb", show.Id.ToString(CultureInfo.InvariantCulture), season.SeasonNumber);
        return new MetadataItem(
            RatingKey: ratingKey,
            Key: $"/library/metadata/{ratingKey}",
            Guid: PlexGuid.Format(providerIdentifier, "season", ratingKey),
            Type: "season",
            Title: string.IsNullOrEmpty(season.Name) ? $"Season {season.SeasonNumber}" : season.Name,
            OriginallyAvailableAt: DateOrNull(season.AirDate),
            Thumb: Rewrite(season.PosterPath, imageBaseUrl) ?? Rewrite(show.PosterPath, imageBaseUrl),
            Art: Rewrite(show.BackdropPath, imageBaseUrl),
            Year: YearOf(season.AirDate) ?? YearOf(show.FirstAirDate),
            Summary: season.Overview,
            ContentRating: PeopleMapper.TvContentRating(ratings, country),
            Index: season.SeasonNumber,
            ParentRatingKey: showKey,
            ParentKey: $"/library/metadata/{showKey}",
            ParentGuid: PlexGuid.Format(providerIdentifier, "show", showKey),
            ParentType: "show",
            ParentTitle: NameOf(show),
            ParentThumb: Rewrite(show.PosterPath, imageBaseUrl),
            ParentArt: Rewrite(show.BackdropPath, imageBaseUrl),
            Children: children is null ? null : new ChildrenObject(children.Count, children));
    }

    // ---- episode ----

    /// <summary>Episode item with full parent/grandparent fields (used for children lists, matches, and metadata).</summary>
    public static MetadataItem ToEpisodeItem(TmdbEpisode episode, TmdbShow show, string providerIdentifier, string imageBaseUrl)
    {
        string showId = show.Id.ToString(CultureInfo.InvariantCulture);
        string ratingKey = RatingKey.Episode("tmdb", showId, episode.SeasonNumber, episode.EpisodeNumber);
        string seasonKey = RatingKey.Season("tmdb", showId, episode.SeasonNumber);
        string showKey = RatingKey.Show("tmdb", showId);

        return new MetadataItem(
            RatingKey: ratingKey,
            Key: $"/library/metadata/{ratingKey}",
            Guid: PlexGuid.Format(providerIdentifier, "episode", ratingKey),
            Type: "episode",
            Title: string.IsNullOrEmpty(episode.Name) ? $"Episode {episode.EpisodeNumber}" : episode.Name,
            OriginallyAvailableAt: DateOrNull(episode.AirDate),
            Thumb: Rewrite(episode.StillPath, imageBaseUrl),
            Art: Rewrite(show.BackdropPath, imageBaseUrl),
            Year: YearOf(episode.AirDate) ?? YearOf(show.FirstAirDate),
            Summary: episode.Overview,
            Duration: episode.Runtime is { } minutes ? minutes * 60_000 : null,
            Rating: episode.VoteAverage > 0
                ? [new RatingItem("themoviedb://image.rating", "audience", episode.VoteAverage)]
                : null,
            Index: episode.EpisodeNumber,
            ParentRatingKey: seasonKey,
            ParentKey: $"/library/metadata/{seasonKey}",
            ParentGuid: PlexGuid.Format(providerIdentifier, "season", seasonKey),
            ParentType: "season",
            ParentTitle: SeasonTitle(show, episode.SeasonNumber),
            ParentThumb: SeasonPoster(show, episode.SeasonNumber, imageBaseUrl),
            ParentArt: Rewrite(show.BackdropPath, imageBaseUrl),
            ParentIndex: episode.SeasonNumber,
            GrandparentRatingKey: showKey,
            GrandparentKey: $"/library/metadata/{showKey}",
            GrandparentGuid: PlexGuid.Format(providerIdentifier, "show", showKey),
            GrandparentType: "show",
            GrandparentTitle: NameOf(show),
            GrandparentThumb: Rewrite(show.PosterPath, imageBaseUrl),
            GrandparentArt: Rewrite(show.BackdropPath, imageBaseUrl),
            GuidItems: [new GuidItem($"tmdb://{episode.Id}")]);
    }

    // ---- helpers ----

    private static IReadOnlyList<GuidItem> BuildShowGuids(TmdbShow show, TmdbExternalIds? externalIds)
    {
        var guids = new List<GuidItem> { new($"tmdb://{show.Id}") };
        if (!string.IsNullOrEmpty(externalIds?.ImdbId))
            guids.Add(new GuidItem($"imdb://{externalIds.ImdbId}"));
        if (externalIds?.TvdbId is { } tvdbId)
            guids.Add(new GuidItem($"tvdb://{tvdbId}"));
        return guids;
    }

    private static string NameOf(TmdbShow show) =>
        string.IsNullOrEmpty(show.Name) ? show.OriginalName ?? string.Empty : show.Name;

    private static string SeasonTitle(TmdbSeasonSummary season) =>
        string.IsNullOrEmpty(season.Name) ? $"Season {season.SeasonNumber}" : season.Name;

    private static string SeasonTitle(TmdbShow show, int seasonNumber) =>
        show.Seasons?.FirstOrDefault(s => s.SeasonNumber == seasonNumber)?.Name ?? $"Season {seasonNumber}";

    private static string? SeasonPoster(TmdbShow show, int seasonNumber, string imageBaseUrl)
    {
        string? path = show.Seasons?.FirstOrDefault(s => s.SeasonNumber == seasonNumber)?.PosterPath;
        return Rewrite(path, imageBaseUrl) ?? Rewrite(show.PosterPath, imageBaseUrl);
    }

    private static bool IsLocalizedRequest(string? language, string? originalLanguage)
    {
        if (language is null || originalLanguage is null)
            return false;
        string primary = language.Split('-')[0];
        return !string.Equals(primary, originalLanguage, StringComparison.OrdinalIgnoreCase);
    }

    private static string? DateOrNull(string? date) => string.IsNullOrEmpty(date) ? null : date;

    private static int? YearOf(string? date)
    {
        if (date is null || date.Length < 4)
            return null;
        return int.TryParse(date.AsSpan(0, 4), NumberStyles.None, CultureInfo.InvariantCulture, out int year)
            ? year
            : null;
    }

    private static string? Rewrite(string? path, string imageBaseUrl) =>
        string.IsNullOrEmpty(path) ? null : ImageCache.RewriteToLocalPath($"{imageBaseUrl.TrimEnd('/')}{path}");
}
