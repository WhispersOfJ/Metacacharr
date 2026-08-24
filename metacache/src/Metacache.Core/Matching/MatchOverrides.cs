using System.Globalization;

namespace Metacache.Core.Matching;

/// <summary>
/// A manual match pin (DESIGN.md §15.10): for a given lookup <see cref="Key"/> (a Plex
/// guid, or a normalized kind:title:year), always resolve the match to
/// <see cref="Target"/> — a tmdb-source rating key such as `tmdb-movie-105`,
/// `tmdb-show-15260`, `tmdb-season-15260-1` or `tmdb-episode-15260-1-1`. Overrides
/// are consulted before any upstream search, so a pinned correction wins over TMDB
/// search and survives Plex refreshes (Plex re-sends the guid it stored).
/// </summary>
public sealed record MatchOverride(
    string Key,
    string Kind,
    string Target,
    string? Notes,
    string CreatedAt);

/// <summary>
/// A persisted record of a match that produced zero candidates (auto mode only), so a
/// human can review failures and pin an override. <see cref="Count"/> is how many times
/// the same failure has been seen.
/// </summary>
public sealed record UnmatchedEntry(
    string Key,
    string Kind,
    string? Title,
    int? Year,
    string? Guid,
    string? Filename,
    string? ParentTitle,
    string? GrandparentTitle,
    int? Index,
    int? ParentIndex,
    string? AirDate,
    int Count,
    string LastSeenAt)
{
    public static UnmatchedEntry FromHint(MatchHint hint, DateTimeOffset now) => new(
        Key: MatchOverrideKeys.ForHint(hint),
        Kind: hint.Kind.ToString().ToLowerInvariant(),
        Title: hint.Title,
        Year: hint.Year,
        Guid: hint.ExternalGuids.Count > 0 ? hint.ExternalGuids[0] : null,
        Filename: hint.Filename,
        ParentTitle: hint.ParentTitle,
        GrandparentTitle: hint.GrandparentTitle,
        Index: hint.Index,
        ParentIndex: hint.ParentIndex,
        AirDate: hint.AirDate,
        Count: 1,
        LastSeenAt: now.ToString("O", CultureInfo.InvariantCulture));
}

/// <summary>
/// Deterministic lookup-key derivation shared by the capture and consult paths, so an
/// entry recorded by the capture path is found by the consult path (and vice versa).
/// </summary>
public static class MatchOverrideKeys
{
    /// <summary>
    /// The override key for a match hint: the request guid when Plex sent one (Plex
    /// re-sends the guid it stored after a manual fix, so a guid-keyed pin fires on
    /// every refresh), otherwise the normalized kind:title:year.
    /// </summary>
    public static string ForHint(MatchHint hint)
    {
        if (hint.ExternalGuids.Count > 0)
            return hint.ExternalGuids[0];

        string? title = hint.Kind switch
        {
            MatchKind.Season => hint.ParentTitle,
            MatchKind.Episode => hint.GrandparentTitle,
            _ => hint.Title
        };
        string normalized = Normalize(title);
        string year = hint.Year?.ToString(CultureInfo.InvariantCulture) ?? "";
        return $"{hint.Kind.ToString().ToLowerInvariant()}:{normalized}:{year}";
    }

    /// <summary>Lowercase, whitespace-collapsed, trimmed — same spirit as the scorer's title normalization.</summary>
    public static string Normalize(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return "";
        return string.Join(' ', value.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries))
            .ToLowerInvariant();
    }
}
