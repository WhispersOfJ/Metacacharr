using System.Text.RegularExpressions;

namespace Metacache.Plex;

/// <summary>
/// Rating-key and GUID utilities per DESIGN.md §5.
///
/// Rating keys identify items inside a provider. They may only contain ASCII
/// letters, digits, dashes and underscores (they become part of the item GUID),
/// and must not contain slashes. Both TMDB- and TVDB-derived keys are supported
/// (hybrid sources) by carrying the source in the first segment.
///
/// Format:        {source}-{kind}-{id}(-{index...})
/// Examples:      tmdb-movie-19934 | tmdb-show-15260 | tmdb-season-4020-1
///                tmdb-episode-4020-1-4 | tvdb-show-78874
/// GUID format:   {providerIdentifier}://{type}/{ratingKey}
/// </summary>
public static class RatingKey
{
    private static readonly Regex ValidKey = new("^[a-zA-Z0-9_-]+$", RegexOptions.Compiled);

    public static string Movie(string source, string id) => $"{source}-movie-{id}";
    public static string Show(string source, string id) => $"{source}-show-{id}";
    public static string Season(string source, string id, int season) => $"{source}-season-{id}-{season}";
    public static string Episode(string source, string id, int season, int episode) => $"{source}-episode-{id}-{season}-{episode}";
    public static string Collection(string source, string id) => $"{source}-collection-{id}";

    /// <summary>True when the key is a well-formed rating key (chars + structure).</summary>
    public static bool IsValid(string key) => TryParse(key, out _);

    /// <summary>Parses a rating key back into its components for upstream routing.</summary>
    public static bool TryParse(string key, out ParsedRatingKey parsed)
    {
        parsed = default!;
        if (string.IsNullOrEmpty(key) || !ValidKey.IsMatch(key))
            return false;

        string[] parts = key.Split('-');
        if (parts.Length < 3)
            return false;

        string source = parts[0];
        string kind = parts[1];
        string id = parts[2];

        // Expected trailing index count is implied by the kind.
        int expectedIndices = kind switch
        {
            "movie" or "show" or "collection" => 0,
            "season" => 1,
            "episode" => 2,
            _ => -1
        };
        if (expectedIndices < 0 || parts.Length != 3 + expectedIndices)
            return false;

        var indices = new int[expectedIndices];
        for (int i = 0; i < expectedIndices; i++)
        {
            if (!int.TryParse(parts[3 + i], out indices[i]))
                return false;
        }

        parsed = new ParsedRatingKey(source, kind, id, indices);
        return true;
    }
}

public sealed record ParsedRatingKey(string Source, string Kind, string Id, int[] Indices);

public static class PlexGuid
{
    public static string Format(string providerIdentifier, string type, string ratingKey) =>
        $"{providerIdentifier}://{type}/{ratingKey}";
}
