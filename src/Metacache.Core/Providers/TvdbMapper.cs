namespace Metacache.Core.Providers;

/// <summary>
/// Adapts TVDB records into the TMDB-shaped models the Plex mappers and the match
/// scorer consume, so the TVDB source plugs in behind TMDB without new mapping code.
/// </summary>
public static class TvdbMapper
{
    public static TmdbEpisode ToTmdbEpisode(TvdbEpisode episode)
    {
        // TVDB episode images are absolute artwork URLs (not TMDB-relative paths), so
        // they can't ride in StillPath — ToEpisodeItem prefixes that with the TMDB
        // image base. Callers rewrite the absolute URL to a local /img/ path directly.
        return new TmdbEpisode(
            Id: episode.Id,
            Name: episode.Name,
            Overview: episode.Overview,
            EpisodeNumber: episode.Number,
            SeasonNumber: episode.SeasonNumber,
            AirDate: episode.Aired,
            StillPath: null,
            Runtime: episode.Runtime,
            VoteAverage: 0)
        {
            FromTvdb = true
        };
    }
}
