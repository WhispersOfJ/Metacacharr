using Metacache.Core.Cache;
using Metacache.Core.Providers;
using Metacache.Plex.Models;

namespace Metacache.Plex.Mappers;

/// <summary>
/// Person and rating mapping shared by the movie and TV mappers: cast/crew arrays and
/// country-aware content ratings (Metadata.md — Role/Director/Producer/Writer, Rating,
/// and the "us/PG vs de/FSK 12" contentRating convention).
/// </summary>
public static class PeopleMapper
{
    private const int MaxCast = 20;
    private const int MaxCrewPerRole = 10;

    public static IReadOnlyList<PersonItem>? ToRoles(TmdbCredits? credits, string imageBaseUrl)
    {
        if (credits?.Cast is null || credits.Cast.Count == 0)
            return null;
        return credits.Cast
            .OrderBy(c => c.Order)
            .Take(MaxCast)
            .Select(c => new PersonItem(
                c.Name ?? "",
                Thumb: Rewrite(c.ProfilePath, imageBaseUrl),
                Role: c.Character,
                Order: c.Order + 1))
            .ToList();
    }

    public static IReadOnlyList<PersonItem>? CrewByJob(TmdbCredits? credits, string job, string imageBaseUrl)
    {
        if (credits?.Crew is null)
            return null;
        var people = credits.Crew
            .Where(c => string.Equals(c.Job, job, StringComparison.OrdinalIgnoreCase))
            .OrderBy(c => c.Order)
            .Take(MaxCrewPerRole)
            .Select(c => new PersonItem(c.Name ?? "", Thumb: Rewrite(c.ProfilePath, imageBaseUrl), Role: job))
            .ToList();
        return people.Count == 0 ? null : people;
    }

    /// <summary>Movie certification for the requested country (default US → bare, e.g. "PG-13"; others prefixed, e.g. "de/FSK 12").</summary>
    public static string? MovieCertification(TmdbReleaseDatesResponse? releaseDates, string? country)
    {
        if (releaseDates?.Results is null)
            return null;
        var entries = releaseDates.Results
            .Select(r => (r.Iso, r.ReleaseDates?.Select(d => d.Certification).ToList() ?? new List<string?>()))
            .ToList();
        return Format(Select(entries, country));
    }

    /// <summary>TV content rating for the requested country (same convention).</summary>
    public static string? TvContentRating(TmdbContentRatingsResponse? ratings, string? country)
    {
        if (ratings?.Results is null)
            return null;
        var entries = ratings.Results
            .Select(r => (r.Iso, new List<string?> { r.Rating }))
            .ToList();
        return Format(Select(entries, country));
    }

    /// <summary>Preferred country first; fall back to the first entry with a non-empty value.</summary>
    private static (string? Iso, string? Value)? Select(IReadOnlyList<(string? Iso, List<string?> Values)> entries, string? country)
    {
        string want = (country ?? "US").ToUpperInvariant();

        // FirstOrDefault on a value-tuple list returns the default tuple (null, null)
        // — never null — so test the tuple's Iso, not the tuple itself, before use.
        var preferred = entries.FirstOrDefault(e => string.Equals(e.Iso, want, StringComparison.OrdinalIgnoreCase));
        (string? Iso, List<string?> Values)? match = preferred.Iso is null ? null : preferred;
        if (match is null || match.Value.Values is not { } values || values.All(string.IsNullOrEmpty))
        {
            var fallback = entries.FirstOrDefault(e => e.Values.Any(v => !string.IsNullOrEmpty(v)));
            match = fallback.Iso is null ? null : fallback;
        }
        if (match is null)
            return null;

        string? value = match.Value.Values.FirstOrDefault(v => !string.IsNullOrEmpty(v));
        return value is null ? null : (match.Value.Iso, value);
    }

    private static string? Format((string? Iso, string? Value)? selected)
    {
        if (selected is null)
            return null;
        string? value = selected.Value.Value;
        if (string.IsNullOrEmpty(value))
            return null;
        if (string.Equals(selected.Value.Iso, "US", StringComparison.OrdinalIgnoreCase))
            return value;
        return $"{selected.Value.Iso?.ToLowerInvariant()}/{value}";
    }

    internal static string? Rewrite(string? path, string imageBaseUrl) =>
        string.IsNullOrEmpty(path) ? null : ImageCache.RewriteToLocalPath($"{imageBaseUrl.TrimEnd('/')}{path}");
}
