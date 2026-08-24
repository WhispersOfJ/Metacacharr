using System.Globalization;
using System.Text.Json;
using Metacache.Core.Cache;
using Metacache.Plex;

namespace Metacache.Host;

/// <summary>
/// The queryable cache index (DESIGN.md §19) — the normalized, warmed library as a
/// local metadata API so tools in the stack (Overseerr, Tautulli, scripts, a future
/// Plex search integration) query Metacache instead of TMDB:
///   GET /items?kind=&q=&guid=&fresh=&limit=  — search the index
///   GET /guid/lookup?guid=…                 — translate across imdb/tmdb/tvdb
/// Both are read-only and served entirely from the local cache when the data is
/// there; guid resolution fetches through the cached TMDB client on first use.
/// </summary>
public static class CacheIndexEndpoints
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    private static readonly string[] Kinds = ["movie", "show", "season", "episode"];

    public static void MapCacheIndexEndpoints(this WebApplication app)
    {
        app.MapGet("/items", async (HttpContext context, CacheStore store, GuidLookupService lookup) =>
            await SearchItemsAsync(context, store, lookup).ConfigureAwait(false));
        app.MapGet("/guid/lookup", async (string? guid, GuidLookupService lookup, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(guid))
                return Results.Json(new { error = "'guid' is required." }, statusCode: StatusCodes.Status400BadRequest);

            GuidLookupResult? result = await lookup.LookupAsync(guid, ct).ConfigureAwait(false);
            return result is null
                ? Results.Json(new { error = $"No title found for guid '{guid}'.", guid }, statusCode: StatusCodes.Status404NotFound)
                : Results.Json(result, Json);
        });
    }

    private static async Task<IResult> SearchItemsAsync(HttpContext context, CacheStore store, GuidLookupService lookup)
    {
        string? kind = context.Request.Query["kind"];
        string? q = context.Request.Query["q"];
        string? guid = context.Request.Query["guid"];
        string? fresh = context.Request.Query["fresh"];
        string? limit = context.Request.Query["limit"];

        if (kind is { Length: > 0 } && !Kinds.Contains(kind))
            return Results.Json(new { error = "'kind' must be one of movie, show, season, episode." },
                statusCode: StatusCodes.Status400BadRequest);

        bool freshOnly = false;
        if (fresh is { Length: > 0 } && !bool.TryParse(fresh, out freshOnly))
            return Results.Json(new { error = "'fresh' must be true or false." }, statusCode: StatusCodes.Status400BadRequest);

        int limitValue = 50;
        if (limit is { Length: > 0 } && (!int.TryParse(limit, NumberStyles.None, CultureInfo.InvariantCulture, out limitValue) || limitValue < 1))
            return Results.Json(new { error = "'limit' must be a positive integer." }, statusCode: StatusCodes.Status400BadRequest);
        limitValue = Math.Min(limitValue, 500);

        IReadOnlyList<string>? sourceIds = null;
        if (!string.IsNullOrWhiteSpace(guid))
        {
            GuidLookupResult? resolved = await lookup.LookupAsync(guid, context.RequestAborted).ConfigureAwait(false);
            if (resolved is null)
                return Results.Json(new { error = $"No title found for guid '{guid}'.", guid }, statusCode: StatusCodes.Status404NotFound);
            if (resolved.TmdbId is { } tmdbId)
                sourceIds = [tmdbId.ToString(CultureInfo.InvariantCulture)];
        }

        string? titleLike = string.IsNullOrWhiteSpace(q) ? null : q.Trim();
        ItemSearchResult result = store.SearchItems(
            new ItemSearch(Kinds: string.IsNullOrEmpty(kind) ? null : [kind], TitleLike: titleLike, SourceIds: sourceIds, FreshOnly: freshOnly, Limit: limitValue),
            DateTimeOffset.UtcNow);

        var items = result.Items.Select(i => new
        {
            id = i.Id,
            kind = i.Kind,
            source = i.Source,
            sourceId = i.SourceId,
            lang = i.Lang,
            title = i.Title,
            year = i.Year,
            fetchedAt = i.FetchedAt,
            expiresAt = i.ExpiresAt
        });
        return Results.Json(new { total = result.Total, items }, Json);
    }
}
