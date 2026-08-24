using System.Globalization;
using System.Text;
using System.Text.Json;
using Metacache.Core.Cache;

namespace Metacache.Host;

/// <summary>
/// M3 metrics dashboard (DESIGN.md §12): hit rate from the live gateway counters,
/// per-kind item counts from the normalized store, and disk usage (image files +
/// SQLite DB). GET /metrics returns one JSON object; GET /metrics/prometheus
/// renders the same data in Prometheus text exposition format for scraping
/// (https://prometheus.io/docs/instrumenting/exposition_formats/).
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

        app.MapGet("/metrics/prometheus", (UpstreamCache cache, CacheStore store, ImageStore images, CacheOptions options) =>
        {
            CacheCounters counters = cache.GetCounters();
            CacheStats stats = store.GetStats();
            (int imageFiles, long imageBytes) = images.DiskUsage();
            long? dbBytes = options.DataSource == ":memory:" ? null : new FileInfo(options.DataSource).Length;

            string body = RenderPrometheus(counters, stats, store.CountItemsByKind(), imageFiles, imageBytes, dbBytes);
            return Results.Text(body, "text/plain; version=0.0.4; charset=utf-8");
        });
    }

    /// <summary>
    /// Renders the cache metrics as Prometheus text exposition format lines
    /// (https://prometheus.io/docs/instrumenting/exposition_formats/). Counters
    /// carry the <c>_total</c> suffix; gauges are plain. Deterministic ordering
    /// for stable scrapes.
    /// </summary>
    internal static string RenderPrometheus(
        CacheCounters counters, CacheStats stats, IReadOnlyDictionary<string, int> itemsByKind,
        int imageFiles, long imageBytes, long? dbBytes)
    {
        var sb = new StringBuilder(512);

        Counter(sb, "metacache_cache_requests_total", "Total upstream-cache lookups (hits + misses) since process start.", counters.Requests);
        Counter(sb, "metacache_cache_hits_total", "Lookups served from the cache without contacting upstream.", counters.Hits);
        Counter(sb, "metacache_cache_misses_total", "Lookups that contacted upstream (cold miss, refresh, or stale-if-error).", counters.Misses);
        Gauge(sb, "metacache_cache_hit_ratio", "Fraction of lookups served from cache (0..1).", counters.HitRate);
        Gauge(sb, "metacache_upstream_entries", "Cached upstream HTTP responses in the SQLite store.", stats.UpstreamEntries);
        Gauge(sb, "metacache_upstream_bytes", "Total body bytes of cached upstream responses.", stats.UpstreamBytes);
        Gauge(sb, "metacache_items_entries", "Normalized metadata items in the store (movies, shows, seasons, episodes).", stats.ItemEntries);
        Gauge(sb, "metacache_images_files", "Artwork files stored on disk by the image cache.", imageFiles);
        Gauge(sb, "metacache_images_bytes", "Total bytes of stored artwork.", imageBytes);

        foreach ((string kind, int count) in itemsByKind.OrderBy(p => p.Key, StringComparer.Ordinal))
            Gauge(sb, "metacache_items_by_kind", "Cached metadata items, labeled by kind.", count, ("kind", kind));

        if (dbBytes is not null)
            Gauge(sb, "metacache_db_bytes", "Size of the SQLite cache file on disk (absent for :memory:).", dbBytes.Value);

        return sb.ToString();
    }

    private static void Counter(StringBuilder sb, string name, string help, long value) =>
        Emit(sb, name, help, "counter", value, null);

    private static void Gauge(StringBuilder sb, string name, string help, double value, (string, string)? label = null) =>
        Emit(sb, name, help, "gauge", value, label);

    private static void Emit(StringBuilder sb, string name, string help, string type, double value, (string, string)? label)
    {
        sb.Append("# HELP ").Append(name).Append(' ').Append(help).Append('\n');
        sb.Append("# TYPE ").Append(name).Append(' ').Append(type).Append('\n');
        sb.Append(name);
        if (label is { } l)
            sb.Append('{').Append(l.Item1).Append("=\"").Append(Escape(l.Item2)).Append('"').Append('}');
        sb.Append(' ').Append(value.ToString("0.######", CultureInfo.InvariantCulture)).Append('\n');
    }

    private static string Escape(string value) =>
        value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n");
}
