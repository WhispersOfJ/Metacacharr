using System.Text.Json;
using Metacache.Core.Cache;

namespace Metacache.Host;

/// <summary>
/// Small admin surface for the cache (first step toward the M3 dashboard):
///   GET  /cache/stats — CacheStore.GetStats() as JSON
///   POST /cache/purge — delete expired rows; returns { "removed": n }
/// Same exposure as the rest of the service: unauthenticated, LAN-only by default.
/// </summary>
public static class CacheAdminEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static void MapCacheAdminEndpoints(this WebApplication app)
    {
        app.MapGet("/cache/stats", (CacheStore store) => Results.Json(store.GetStats(), JsonOptions));

        app.MapPost("/cache/purge", (CacheStore store) =>
        {
            int removed = store.PurgeExpired();
            return Results.Json(new { removed }, JsonOptions);
        });
    }
}
