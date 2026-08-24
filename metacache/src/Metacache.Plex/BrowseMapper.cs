using Metacache.Core;
using Metacache.Core.Cache;
using Metacache.Plex.Models;

namespace Metacache.Plex;

/// <summary>
/// Maps normalized index rows to Plex-shaped browse items (DESIGN.md §21). Only
/// movies and shows are browse rows — seasons/episodes live in the /items index but
/// aren't library-browse entries. Thumbs point at the sized-variant endpoint
/// (/img/{hash}?width=…) so list views load small images from the local cache.
/// </summary>
public static class BrowseMapper
{
    /// <summary>The longest-side size browse lists request for thumbs.</summary>
    public const int ThumbWidth = 185;

    public static MetadataItem? ToBrowseItem(CachedItem item)
    {
        string? ratingKey = item.Kind switch
        {
            "movie" => RatingKey.Movie("tmdb", item.SourceId),
            "show" => RatingKey.Show("tmdb", item.SourceId),
            _ => null
        };
        if (ratingKey is null)
            return null;

        string identifier = item.Kind == "movie" ? ProviderIdentities.Movie : ProviderIdentities.Tv;
        return new MetadataItem(
            RatingKey: ratingKey,
            Key: $"/library/metadata/{ratingKey}",
            Guid: PlexGuid.Format(identifier, item.Kind, ratingKey),
            Type: item.Kind,
            Title: string.IsNullOrEmpty(item.Title) ? ratingKey : item.Title,
            Year: item.Year,
            Thumb: item.Thumb is null ? null : $"{item.Thumb}?width={ThumbWidth}");
    }
}
