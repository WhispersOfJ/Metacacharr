using System.Globalization;
using Metacache.Core.Cache;
using Metacache.Core.Providers;
using Metacache.Plex.Models;

namespace Metacache.Plex.Mappers;

/// <summary>
/// Maps TMDB movie data onto Plex's provider schema (Metadata.md). This is the movie
/// half of the Mapper layer — the one place that knows how upstream data becomes Plex
/// JSON. Artwork URLs are rewritten through <see cref="ImageCache.RewriteToLocalPath"/>
/// so Plex always fetches art from Metacache's own /img endpoint (DESIGN.md §7.3).
/// </summary>
public static class MovieMapper
{
    /// <summary>Compact item for match responses (type/ratingKey/guid/title/year/thumb).</summary>
    public static MetadataItem ToMatchItem(TmdbMovie movie, string providerIdentifier, string imageBaseUrl, string? language)
    {
        string ratingKey = RatingKey.Movie("tmdb", movie.Id.ToString(CultureInfo.InvariantCulture));
        return new MetadataItem(
            RatingKey: ratingKey,
            Key: $"/library/metadata/{ratingKey}",
            Guid: PlexGuid.Format(providerIdentifier, "movie", ratingKey),
            Type: "movie",
            Title: TitleOf(movie),
            OriginallyAvailableAt: DateOrNull(movie.ReleaseDate),
            Thumb: Rewrite(movie.PosterPath, imageBaseUrl),
            Year: YearOf(movie.ReleaseDate));
    }

    /// <summary>Full metadata item for GET /library/metadata/{ratingKey}.</summary>
    public static MetadataItem ToMetadata(TmdbMovie movie, string providerIdentifier, string imageBaseUrl, string? language)
    {
        string ratingKey = RatingKey.Movie("tmdb", movie.Id.ToString(CultureInfo.InvariantCulture));
        string title = TitleOf(movie);
        bool localized = IsLocalizedRequest(language, movie.OriginalLanguage);

        return new MetadataItem(
            RatingKey: ratingKey,
            Key: $"/library/metadata/{ratingKey}",
            Guid: PlexGuid.Format(providerIdentifier, "movie", ratingKey),
            Type: "movie",
            Title: title,
            OriginallyAvailableAt: DateOrNull(movie.ReleaseDate),
            Thumb: Rewrite(movie.PosterPath, imageBaseUrl),
            Art: Rewrite(movie.BackdropPath, imageBaseUrl),
            OriginalTitle: localized ? movie.OriginalTitle : null,
            Year: YearOf(movie.ReleaseDate),
            Summary: movie.Overview,
            IsAdult: movie.Adult ? true : null,
            Duration: movie.Runtime is { } minutes ? minutes * 60_000 : null,
            Tagline: movie.Tagline,
            Studio: movie.ProductionCompanies?.FirstOrDefault()?.Name,
            Image: BuildImages(movie, imageBaseUrl),
            Genre: movie.Genres is null ? null : movie.Genres.Select(g => new GenreItem(g.Name ?? "")).ToList(),
            GuidItems: BuildGuids(movie),
            Rating: movie.VoteAverage > 0
                ? [new RatingItem("themoviedb://image.rating", "audience", movie.VoteAverage)]
                : null,
            Country: movie.ProductionCountries is null ? null
                : movie.ProductionCountries.Select(c => new CountryItem(c.Name ?? "")).ToList(),
            StudioItems: movie.ProductionCompanies is null ? null
                : movie.ProductionCompanies.Select(c => new StudioItem(c.Name ?? "")).ToList());
    }

    internal static IReadOnlyList<ImageAsset>? BuildImages(TmdbMovie movie, string imageBaseUrl)
    {
        var images = new List<ImageAsset>();
        if (Rewrite(movie.PosterPath, imageBaseUrl) is { } poster)
            images.Add(new ImageAsset("coverPoster", poster, TitleOf(movie)));
        if (Rewrite(movie.BackdropPath, imageBaseUrl) is { } backdrop)
            images.Add(new ImageAsset("background", backdrop, TitleOf(movie)));
        return images.Count == 0 ? null : images;
    }

    private static IReadOnlyList<GuidItem>? BuildGuids(TmdbMovie movie)
    {
        var guids = new List<GuidItem> { new($"tmdb://{movie.Id}") };
        if (!string.IsNullOrEmpty(movie.ImdbId))
            guids.Add(new GuidItem($"imdb://{movie.ImdbId}"));
        return guids;
    }

    private static string TitleOf(TmdbMovie movie) =>
        string.IsNullOrEmpty(movie.Title) ? movie.OriginalTitle ?? string.Empty : movie.Title;

    private static bool IsLocalizedRequest(string? language, string? originalLanguage)
    {
        if (language is null || originalLanguage is null)
            return false;
        string primary = language.Split('-')[0];
        return !string.Equals(primary, originalLanguage, StringComparison.OrdinalIgnoreCase);
    }

    private static string? DateOrNull(string? releaseDate) =>
        string.IsNullOrEmpty(releaseDate) ? null : releaseDate;

    private static int? YearOf(string? releaseDate)
    {
        if (releaseDate is null || releaseDate.Length < 4)
            return null;
        return int.TryParse(releaseDate.AsSpan(0, 4), NumberStyles.None, CultureInfo.InvariantCulture, out int year)
            ? year
            : null;
    }

    /// <summary>Rewrites an upstream image URL (built from the image base + path) to /img/{hash}.</summary>
    private static string? Rewrite(string? path, string imageBaseUrl) =>
        string.IsNullOrEmpty(path) ? null : ImageCache.RewriteToLocalPath($"{imageBaseUrl.TrimEnd('/')}{path}");
}
