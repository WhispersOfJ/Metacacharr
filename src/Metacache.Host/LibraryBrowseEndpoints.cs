using System.Globalization;
using Metacache.Core;
using Metacache.Core.Cache;
using Metacache.Plex;
using Metacache.Plex.Models;

namespace Metacache.Host;

/// <summary>
/// The library browse surface (DESIGN.md §21) — search and recently-added, answered
/// entirely from the warmed cache index with Plex-shaped containers, so a library can
/// be browsed offline:
///   GET /library/search?title=&kind=movie|show&year=&page headers
///   GET /library/recentlyAdded  (most recently warmed items)
/// Both page via the standard X-Plex-Container-Size/Start headers, return movies and
/// shows (seasons/episodes are /items territory), and point thumbs at the sized
/// variant endpoint (/img/{hash}?width=185).
/// </summary>
public static class LibraryBrowseEndpoints
{
    /// <summary>Container identifier for mixed-kind browse responses.</summary>
    private const string GenericIdentifier = "tv.plex.agents.custom.metacache";

    public static void MapLibraryBrowseEndpoints(this WebApplication app)
    {
        app.MapGet("/library/search", (HttpContext context, CacheStore store) => Search(context, store));
        app.MapGet("/library/recentlyAdded", (HttpContext context, CacheStore store) => RecentlyAdded(context, store));
    }

    private static IResult Search(HttpContext context, CacheStore store)
    {
        string? kind = context.Request.Query["kind"];
        if (kind is { Length: > 0 } && kind is not ("movie" or "show"))
            return Results.Json(new { error = "'kind' must be movie or show." }, statusCode: StatusCodes.Status400BadRequest);

        int? year = null;
        string? rawYear = context.Request.Query["year"];
        if (!string.IsNullOrEmpty(rawYear))
        {
            if (!int.TryParse(rawYear, NumberStyles.None, CultureInfo.InvariantCulture, out int parsed) || parsed < 1)
                return Results.Json(new { error = "'year' must be a positive integer." }, statusCode: StatusCodes.Status400BadRequest);
            year = parsed;
        }

        string? title = context.Request.Query["title"];
        ItemSearchResult result = store.SearchItems(new ItemSearch(
            Kinds: string.IsNullOrEmpty(kind) ? ["movie", "show"] : [kind],
            TitleLike: string.IsNullOrWhiteSpace(title) ? null : title.Trim(),
            Year: year,
            Limit: PlexPaging.PageSize(context.Request),
            Offset: PlexPaging.StartOffset(context.Request)), DateTimeOffset.UtcNow);
        return Container(result, kind, PlexPaging.StartOffset(context.Request));
    }

    private static IResult RecentlyAdded(HttpContext context, CacheStore store)
    {
        ItemSearchResult result = store.SearchItems(new ItemSearch(
            Kinds: ["movie", "show"],
            RecentFirst: true,
            Limit: PlexPaging.PageSize(context.Request),
            Offset: PlexPaging.StartOffset(context.Request)), DateTimeOffset.UtcNow);
        return Container(result, null, PlexPaging.StartOffset(context.Request));
    }

    private static IResult Container(ItemSearchResult result, string? kind, int offset)
    {
        var items = result.Items
            .Select(BrowseMapper.ToBrowseItem)
            .Where(i => i is not null)
            .Cast<MetadataItem>()
            .ToList();

        string identifier = kind switch
        {
            "movie" => ProviderIdentities.Movie,
            "show" => ProviderIdentities.Tv,
            _ => GenericIdentifier
        };
        var container = new MetadataContainer(
            Offset: offset,
            TotalSize: result.Total,
            Identifier: identifier,
            Size: items.Count,
            Metadata: items);
        return Results.Json(new MetadataContainerResponse(container), ProviderJson.Options);
    }
}
