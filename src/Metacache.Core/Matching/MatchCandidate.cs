namespace Metacache.Core.Matching;

/// <summary>
/// One candidate item to score against a <see cref="MatchHint"/>. Callers (the M1/M2
/// clients) supply these; the scorer never touches the network.
///
/// TV structure fields apply to season/episode candidates: <see cref="ParentTitle"/> is
/// always the SHOW's title (both for seasons and episodes), <see cref="Index"/> is the
/// season number for seasons and the episode number for episodes, <see cref="ParentIndex"/>
/// is the season number for episodes, and <see cref="AirDate"/> the episode air date.
/// </summary>
/// <param name="Id">Provider identity of the item (e.g. the TMDB id).</param>
/// <param name="Title">Display title (e.g. "Season 8", the episode title, or a movie title).</param>
/// <param name="OriginalTitle">Title in the item's original language, when known.</param>
/// <param name="Year">Release year (movie/show), when known.</param>
/// <param name="OriginalLanguage">ISO-639-1 code of the item's original language.</param>
/// <param name="Popularity">Provider popularity metric (tiebreaker).</param>
/// <param name="Adult">Explicit content flag.</param>
/// <param name="ExternalIds">Provider ids in Plex format: "imdb://tt0088763", "tmdb://105".</param>
/// <param name="ParentTitle">Show title for seasons/episodes.</param>
/// <param name="Index">Season number (season) or episode number (episode).</param>
/// <param name="ParentIndex">Season number (episode only).</param>
/// <param name="AirDate">Air date as yyyy-MM-dd (episode only).</param>
public sealed record MatchCandidate(
    string Id,
    string Title,
    string? OriginalTitle,
    int? Year,
    string? OriginalLanguage,
    double Popularity,
    bool Adult,
    IReadOnlyList<string> ExternalIds,
    string? ParentTitle = null,
    int? Index = null,
    int? ParentIndex = null,
    string? AirDate = null);
