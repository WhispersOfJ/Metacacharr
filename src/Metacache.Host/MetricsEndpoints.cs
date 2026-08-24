using System.Text.Json;
using Metacache.Core.Cache;

namespace Metacache.Host;

/// <summary>
/// M3 metrics dashboard (DESIGN.md §12): hit rate from the live gateway counters,
/// per-kind item counts from the normalized store, and disk usage (image files +
/// SQLite DB). GET /metrics returns one JSON object.
/// </summary>
public static class MetricsEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static void MapMetricsEndpoints(this WebApplication app)
    {
        app.MapGet("/metrics", (UpstreamCache cache, CacheStore store, ImageStore images, CacheOptions options) =>
        {
            CacheCounters counters = cache.GetCounters();
            CacheStats stats = store.GetStats();
            (int imageFiles, long imageBytes) = images.DiskUsage();
            long? dbBytes = options.DataSource == ":memory:" ? null : new FileInfo(options.DataSource).Length;

            var payload = new
            {
                hitRate = Math.Round(counters.HitRate, 4),
                requests = counters.Requests,
                hits = counters.Hits,
                misses = counters.Misses,
                upstreamEntries = stats.UpstreamEntries,
                upstreamBytes = stats.UpstreamBytes,
                itemEntries = stats.ItemEntries,
                itemsByKind = store.CountItemsByKind(),
                images = new { files = imageFiles, bytes = imageBytes },
                dbBytes
            };
            return Results.Json(payload, JsonOptions);
        });
    }
}
