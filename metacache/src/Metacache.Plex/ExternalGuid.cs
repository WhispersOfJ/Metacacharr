namespace Metacache.Plex;

/// <summary>
/// Parses the external guids Plex sends in match requests (§6.3 `guid`) into a
/// (source, id) pair for upstream resolution. Handles "imdb://tt0088763",
/// "tmdb://105", "tvdb://152831", and Metacache's own provider guids
/// ("tv.plex.agents.custom.metacache.movie://movie/tmdb-movie-19934" → tmdb/19934).
/// </summary>
public static class ExternalGuid
{
    public static bool TryParse(string guid, out string source, out string id)
    {
        source = "";
        id = "";

        int separator = guid.IndexOf("://", StringComparison.Ordinal);
        if (separator <= 0)
            return false;

        string scheme = guid[..separator];
        string rest = guid[(separator + 3)..];
        int slash = rest.LastIndexOf('/');
        string candidate = slash >= 0 ? rest[(slash + 1)..] : rest;
        if (candidate.Length == 0)
            return false;

        // Metacache rating key (e.g. "tmdb-movie-19934") — carries source + id directly.
        if (RatingKey.TryParse(candidate, out var parsed))
        {
            source = parsed.Source;
            id = parsed.Id;
            return true;
        }

        if (scheme is "imdb" or "tmdb" or "tvdb")
        {
            source = scheme;
            id = candidate;
            return true;
        }

        return false;
    }
}
