namespace Metacache.Core.Matching;

/// <summary>
/// Weights and thresholds for match scoring (DESIGN.md §15.3–15.4, §15.7). Isolated so
/// they can be tuned from configuration once the dashboard exists. Movie/show and
/// season/episode matching use separate weight sets: TV structure (index/air-date) is a
/// hard-ish gate, so it gets the largest share.
/// </summary>
public sealed record MatchPolicy(
    // movie / show
    double TitleWeight = 0.45,
    double YearWeight = 0.25,
    double FilenameWeight = 0.20,
    double PopularityWeight = 0.10,
    // thresholds / shaping
    double AutoMatchThreshold = 0.60,
    double ManualMinScore = 0.15,
    int MaxManualResults = 20,
    double LanguageBonus = 0.02,
    // season / episode
    double TvTitleWeight = 0.40,
    double TvStructureWeight = 0.35,
    double TvFilenameWeight = 0.15,
    double TvPopularityWeight = 0.10)
{
    public static MatchPolicy Default { get; } = new();
}
