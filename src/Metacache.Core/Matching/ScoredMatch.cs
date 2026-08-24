namespace Metacache.Core.Matching;

/// <summary>A candidate plus its total score (0..1) and component breakdown.</summary>
public sealed record ScoredMatch(MatchCandidate Candidate, double Score, MatchBreakdown Breakdown);

/// <summary>
/// Per-component scores for diagnostics and tuning (DESIGN.md §15.3/§15.7).
/// <see cref="Structure"/> is only used for season/episode matching (index/air-date gate);
/// <see cref="Year"/> is 0 for TV kinds.
/// </summary>
public sealed record MatchBreakdown(
    double Title,
    double Year,
    double Filename,
    double Popularity,
    double LanguageBonus,
    bool GuidExact,
    double Structure = 0);
