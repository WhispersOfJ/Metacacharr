namespace Metacache.Core.Matching;

/// <summary>What kind of item a match request targets (Plex types 1–4).</summary>
public enum MatchKind
{
    Movie,
    Show,
    Season,
    Episode
}

/// <summary>
/// The normalized form of a Plex match request (§6.3 / DESIGN.md §15.1), independent of
/// the provider API so the scoring engine stays pure and testable. The Plex layer maps
/// its request body onto this.
///
/// Plex hint semantics by kind:
/// - movie/show: <see cref="Title"/> + <see cref="Year"/>
/// - season:     <see cref="ParentTitle"/> (the show title) + <see cref="Index"/> (season number)
/// - episode:    <see cref="GrandparentTitle"/> (the show title), <see cref="ParentIndex"/>
///               (season number), <see cref="Index"/> (episode number), or <see cref="AirDate"/>
/// </summary>
public sealed record MatchHint(
    string? Title,
    int? Year,
    string? Filename,
    IReadOnlyList<string> ExternalGuids,
    bool Manual,
    bool IncludeAdult,
    string? Language,
    MatchKind Kind = MatchKind.Movie,
    string? ParentTitle = null,
    string? GrandparentTitle = null,
    int? Index = null,
    int? ParentIndex = null,
    string? AirDate = null)
{
    public static MatchHint Empty { get; } =
        new(null, null, null, [], Manual: false, IncludeAdult: false, Language: null);
}
