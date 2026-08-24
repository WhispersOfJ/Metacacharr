using System.Globalization;
using System.Text.Json;
using Metacache.Core.Cache;
using Microsoft.AspNetCore.Http;

namespace Metacache.Host;

/// <summary>
/// Admin endpoints for the interactive dashboard: per-item inspection, upstream cache
/// entry browsing, and selective purge. These complement the existing /cache/stats and
/// /admin/overrides endpoints.
/// </summary>
public static class AdminEndpoints
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public static void MapAdminEndpoints(this WebApplication app)
    {
        // Per-item search: wraps CacheStore.SearchItems with admin-friendly parameters
        app.MapGet("/admin/items", (HttpContext context, CacheStore store) =>
        {
            var query = context.Request.Query;
            string? kind = query["kind"];
            string? q = query["q"];
            string? fresh = query["fresh"];
            string? limit = query["limit"];

            bool freshOnly = false;
            if (fresh is { Length: > 0 } && !bool.TryParse(fresh, out freshOnly))
                return Results.Json(new { error = "'fresh' must be true or false." }, statusCode: 400);

            int limitValue = 50;
            if (limit is { Length: > 0 } && (!int.TryParse(limit, NumberStyles.None, CultureInfo.InvariantCulture, out limitValue) || limitValue < 1))
                return Results.Json(new { error = "'limit' must be a positive integer." }, statusCode: 400);
            limitValue = Math.Min(limitValue, 500);

            var search = new ItemSearch(
                Kinds: string.IsNullOrEmpty(kind) ? null : [kind],
                TitleLike: string.IsNullOrEmpty(q) ? null : q,
                FreshOnly: freshOnly,
                Limit: limitValue);

            var result = store.SearchItems(search, DateTimeOffset.UtcNow);
            return Results.Json(new
            {
                total = result.Total,
                items = result.Items.Select(i => new
                {
                    i.Id,
                    i.Kind,
                    i.Title,
                    i.Year,
                    i.Thumb,
                    i.SourceId,
                    i.FetchedAt,
                    i.ExpiresAt,
                    fresh = i.ExpiresAt > DateTimeOffset.UtcNow
                })
            }, Json);
        });

        // Single item detail
        app.MapGet("/admin/items/{id}", (string id, CacheStore store) =>
        {
            // Try movie first, then show — we need a lang, use "en"
            var item = store.GetItem(id, "en");
            return item is not null
                ? Results.Json(item, Json)
                : Results.NotFound(new { error = $"Item '{id}' not found." });
        });

        // Upstream cache entries: list recent entries with stats
        app.MapGet("/admin/upstream", (HttpContext context, CacheStore store) =>
        {
            var query = context.Request.Query;
            string? limit = query["limit"];
            int limitValue = 50;
            if (limit is { Length: > 0 } && (!int.TryParse(limit, NumberStyles.None, CultureInfo.InvariantCulture, out limitValue) || limitValue < 1))
                limitValue = 50;
            limitValue = Math.Min(limitValue, 500);

            // GetStats gives us the summary; for individual entries we'd need a new query.
            // For now, return stats + the oldest URLs (which are the eviction candidates).
            var stats = store.GetStats();
            var oldest = store.GetOldestUrls(Math.Min(limitValue, 20));
            return Results.Json(new
            {
                stats,
                evictionCandidates = oldest.Select(u => new
                {
                    u.Hash,
                    u.Url,
                    u.Size,
                    u.FetchedAt
                })
            }, Json);
        });

        // Selective purge: remove expired entries, or entries older than N days
        app.MapPost("/admin/purge/selective", async (HttpContext context, CacheStore store) =>
        {
            using var body = await System.Text.Json.JsonDocument.ParseAsync(context.Request.Body).ConfigureAwait(false);
            var root = body.RootElement;

            int removed = 0;
            if (root.TryGetProperty("expired", out var expiredProp) && expiredProp.GetBoolean())
            {
                removed += store.PurgeExpired();
            }

            // Purge oldest image files if requested
            if (root.TryGetProperty("imageBytes", out var bytesProp))
            {
                long maxBytes = bytesProp.GetInt64();
                if (maxBytes > 0)
                {
                    long current = store.SumUrlBytes();
                    while (current > maxBytes)
                    {
                        var oldest = store.GetOldestUrls(10);
                        if (oldest.Count == 0) break;
                        foreach (var url in oldest)
                        {
                            store.DeleteUrl(url.Hash);
                            current -= url.Size;
                            removed++;
                        }
                    }
                }
            }

            return Results.Json(new { removed }, Json);
        });

        // Database info: schema version, table counts, sizes
        app.MapGet("/admin/database", (CacheStore store) =>
        {
            var stats = store.GetStats();
            return Results.Json(new
            {
                stats.UpstreamEntries,
                stats.ItemEntries,
                stats.UrlEntries,
                stats.UpstreamBytes,
                imageBytes = store.SumUrlBytes()
            }, Json);
        });
    }
}
