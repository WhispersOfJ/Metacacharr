using System.Globalization;
using Metacache.Core.Cache;
using Metacache.Core.Providers;

namespace Metacache.Plex;

/// <summary>
/// The resolved equivalence set for one GUID (DESIGN.md §19): the same title expressed
/// as imdb://, tmdb:// and tvdb:// references. <see cref="ItemId"/> is the item's id in
/// the local index (null when the title isn't in the warmed library), and
/// <see cref="Cached"/> reports whether the item is in that index.
/// </summary>
public sealed record GuidLookupResult(
    string Guid,
    string? Kind,
    string? Title,
    int? Year,
    string? Imdb,
    string? Tmdb,
    string? Tvdb,
    int? TmdbId,
    string? ItemId,
    bool Cached);

/// <summary>
/// Translates any supported GUID — imdb://, tvdb://, tmdb://, tmdb-movie-105 style
/// rating keys, or bare tt…/digit forms — to all its equivalents, resolving through
/// the cache-backed TMDB client (first lookup pays upstream; repeats are cache hits).
/// The local items index disambiguates bare tmdb ids (movie vs show) when possible.
/// </summary>
public sealed class GuidLookupService
{
    private readonly TmdbClient _tmdb;
    private readonly CacheStore _store;

    public GuidLookupService(TmdbClient tmdb, CacheStore store)
    {
        _tmdb = tmdb;
        _store = store;
    }

    /// <summary>Resolves the guid, or null when it's malformed or unknown upstream.</summary>
    public async Task<GuidLookupResult?> LookupAsync(string input, CancellationToken cancellationToken = default)
    {
        Parsed? parsed = Parse(input);
        if (parsed is null)
            return null;

        switch (parsed.Source)
        {
            case "imdb":
                return await FromImdbAsync(parsed.Id, cancellationToken).ConfigureAwait(false);
            case "tvdb":
                return await FromTvdbAsync(parsed.Id, cancellationToken).ConfigureAwait(false);
            default:
                return await FromTmdbAsync(parsed.Id, parsed.KindHint, cancellationToken).ConfigureAwait(false);
        }
    }

    // ---- parsers ----

    private sealed record Parsed(string Source, string Id, string? KindHint);

    private static Parsed? Parse(string input)
    {
        if (string.IsNullOrWhiteSpace(input))
            return null;
        string value = input.Trim();

        if (value.StartsWith("imdb://", StringComparison.OrdinalIgnoreCase))
            return new Parsed("imdb", value[7..], null);
        if (value.StartsWith("tvdb://", StringComparison.OrdinalIgnoreCase))
            return new Parsed("tvdb", value[7..], null);
        if (value.StartsWith("tmdb://", StringComparison.OrdinalIgnoreCase))
            return new Parsed("tmdb", value[7..], null);

        // Plex rating-key style: tmdb-movie-105 / tmdb-show-15260 / tmdb-season-… / tmdb-episode-…
        // Season/episode keys resolve at the show level (the equivalents describe the title).
        if (value.StartsWith("tmdb-", StringComparison.OrdinalIgnoreCase)
            && RatingKey.TryParse(value, out ParsedRatingKey ratingKey))
            return new Parsed("tmdb", ratingKey.Id, ratingKey.Kind == "movie" ? "movie" : "show");

        if (value.StartsWith("tt", StringComparison.OrdinalIgnoreCase))
            return new Parsed("imdb", value, null);
        if (int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out _))
            return new Parsed("tmdb", value, null);

        return null;
    }

    // ---- resolvers ----

    private async Task<GuidLookupResult?> FromImdbAsync(string imdbId, CancellationToken ct)
    {
        IReadOnlyList<TmdbMovieSummary> movies = await _tmdb.FindByExternalIdAsync("imdb_id", imdbId, null, ct).ConfigureAwait(false);
        if (movies.Count > 0)
            return await FromMovieAsync(movies[0].Id, ct).ConfigureAwait(false);

        IReadOnlyList<TmdbShowSummary> shows = await _tmdb.FindTvByExternalIdAsync("imdb_id", imdbId, null, ct).ConfigureAwait(false);
        if (shows.Count > 0)
            return await FromShowAsync(shows[0].Id, ct).ConfigureAwait(false);

        return null;
    }

    private async Task<GuidLookupResult?> FromTvdbAsync(string tvdbId, CancellationToken ct)
    {
        IReadOnlyList<TmdbShowSummary> shows = await _tmdb.FindTvByExternalIdAsync("tvdb_id", tvdbId, null, ct).ConfigureAwait(false);
        return shows.Count > 0 ? await FromShowAsync(shows[0].Id, ct).ConfigureAwait(false) : null;
    }

    private async Task<GuidLookupResult?> FromTmdbAsync(string idText, string? kindHint, CancellationToken ct)
    {
        if (!int.TryParse(idText, NumberStyles.None, CultureInfo.InvariantCulture, out int tmdbId))
            return null;

        // The local index disambiguates bare tmdb ids (movie vs show) when it has them.
        string? kind = kindHint ?? IndexedKind(tmdbId);
        if (kind is "movie")
            return await FromMovieAsync(tmdbId, ct).ConfigureAwait(false);
        if (kind is "show")
            return await FromShowAsync(tmdbId, ct).ConfigureAwait(false);

        // Unknown: probe show first, then movie; 404 means the id isn't that kind.
        try
        {
            return await FromShowAsync(tmdbId, ct).ConfigureAwait(false);
        }
        catch (TmdbNotFoundException)
        {
        }
        try
        {
            return await FromMovieAsync(tmdbId, ct).ConfigureAwait(false);
        }
        catch (TmdbNotFoundException)
        {
            return null;
        }
    }

    private async Task<GuidLookupResult?> FromMovieAsync(int tmdbId, CancellationToken ct)
    {
        TmdbMovie movie = await _tmdb.GetMovieAsync(tmdbId, null, ct).ConfigureAwait(false);
        return Build("movie", movie.Title, YearOf(movie.ReleaseDate),
            movie.ImdbId, tmdbId, null, ct);
    }

    private async Task<GuidLookupResult?> FromShowAsync(int tmdbId, CancellationToken ct)
    {
        TmdbShow show = await _tmdb.GetShowAsync(tmdbId, null, ct).ConfigureAwait(false);
        TmdbExternalIds external = await _tmdb.GetShowExternalIdsAsync(tmdbId, ct).ConfigureAwait(false);
        return Build("show", show.Name, YearOf(show.FirstAirDate),
            external.ImdbId, tmdbId, external.TvdbId, ct);
    }

    private GuidLookupResult? Build(
        string kind, string? title, int? year, string? imdb, int? tmdb, int? tvdb, CancellationToken ct)
    {
        string? itemId = IndexedItemId(tmdb!.Value, kind);
        return new GuidLookupResult(
            Guid: Canonical(kind, imdb, tmdb, tvdb),
            Kind: kind,
            Title: title,
            Year: year,
            Imdb: imdb is null ? null : $"imdb://{imdb}",
            Tmdb: $"tmdb://{tmdb}",
            Tvdb: tvdb is null ? null : $"tvdb://{tvdb}",
            TmdbId: tmdb,
            ItemId: itemId,
            Cached: itemId is not null);
    }

    /// <summary>The input the caller most likely used, for echo — the preferred guid is imdb, then tvdb, then tmdb.</summary>
    private static string Canonical(string kind, string? imdb, int? tmdb, int? tvdb)
    {
        if (imdb is not null)
            return $"imdb://{imdb}";
        if (tvdb is not null)
            return $"tvdb://{tvdb}";
        return $"tmdb://{tmdb}";
    }

    private string? IndexedKind(int tmdbId)
    {
        ItemSearchResult result = _store.SearchItems(
            new ItemSearch(SourceIds: [tmdbId.ToString(CultureInfo.InvariantCulture)], Limit: 1),
            DateTimeOffset.UtcNow);
        return result.Items.Count > 0 ? result.Items[0].Kind : null;
    }

    private string? IndexedItemId(int tmdbId, string kind)
    {
        ItemSearchResult result = _store.SearchItems(
            new ItemSearch(Kinds: [kind], SourceIds: [tmdbId.ToString(CultureInfo.InvariantCulture)], Limit: 1),
            DateTimeOffset.UtcNow);
        return result.Items.Count > 0 ? result.Items[0].Id : null;
    }

    private static int? YearOf(string? date)
    {
        if (date is null || date.Length < 4)
            return null;
        return int.TryParse(date.AsSpan(0, 4), NumberStyles.None, CultureInfo.InvariantCulture, out int year)
            ? year
            : null;
    }
}
