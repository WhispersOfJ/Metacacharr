using System.Globalization;
using System.Text;
using System.Text.Json;
using Metacache.Core.Cache;
using Metacache.Core.Providers;
using Metacache.Plex.Warming;

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
        app.MapGet("/metrics", (UpstreamCache cache, CacheStore store, ImageStore images, CacheOptions options, ScrapeHistory scrapes) =>
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
                dbBytes,
                // The dashboard overlays this against its own 3 s polling (DESIGN §18).
                scrapeHistory = scrapes.Snapshot()
            };
            return Results.Json(payload, JsonOptions);
        });

        app.MapGet("/metrics/prometheus", (UpstreamCache cache, CacheStore store, ImageStore images, CacheOptions options, CacheWarmer warmer, UpstreamMetrics upstreamMetrics, ScrapeHistory scrapes) =>
        {
            CacheCounters counters = cache.GetCounters();
            CacheStats stats = store.GetStats();
            (int imageFiles, long imageBytes) = images.DiskUsage();
            long? dbBytes = options.DataSource == ":memory:" ? null : new FileInfo(options.DataSource).Length;

            // A Prometheus scrape lands here — snapshot the counters for the overlay.
            scrapes.Record(new ScrapePoint(
                DateTimeOffset.UtcNow.ToUnixTimeSeconds(), counters.HitRate, counters.Hits, counters.Requests));

            string body = RenderPrometheus(
                counters, stats, store.CountItemsByKind(), imageFiles, imageBytes, dbBytes,
                warmer.Status, upstreamMetrics.Snapshot());
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
        int imageFiles, long imageBytes, long? dbBytes, WarmStatus? warm = null,
        UpstreamMetricsSnapshot? upstream = null)
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

        // Warm-run status (M3 /warm): the rules file alerts on errors and staleness.
        Gauge(sb, "metacache_warm_running", "1 while a warm run is in flight.", warm?.IsRunning == true ? 1 : 0);
        if (warm?.LastResult is { } last)
        {
            Gauge(sb, "metacache_warm_last_items", "Items warmed by the most recent run, by source.", last.ItemsWarmed, ("source", last.Source));
            Gauge(sb, "metacache_warm_last_images", "Artwork images warmed by the most recent run, by source.", last.ImagesWarmed, ("source", last.Source));
            Gauge(sb, "metacache_warm_last_missing", "Items skipped as missing by the most recent run, by source.", last.Missing, ("source", last.Source));
            Gauge(sb, "metacache_warm_last_errors", "Items that failed to warm in the most recent run, by source.", last.Errors, ("source", last.Source));
            Gauge(sb, "metacache_warm_last_success", "1 when the most recent run completed without errors.", last.Errors == 0 ? 1 : 0, ("source", last.Source));
        }
        if (warm?.CompletedAt is { } completed)
            Gauge(sb, "metacache_warm_last_timestamp_seconds", "Unix time of the most recent warm attempt completion (success or failure).", completed.ToUnixTimeSeconds());

        // Upstream request durations (real upstream requests only, cache hits excluded).
        if (upstream is not null)
        {
            const string hist = "metacache_upstream_request_duration_seconds";
            sb.Append("# HELP ").Append(hist).Append(" Time spent waiting on upstream providers (cache hits excluded).\n");
            sb.Append("# TYPE ").Append(hist).Append(" histogram\n");
            foreach (ProviderDurationHistogram h in upstream.Histograms)
            {
                for (int i = 0; i < h.BucketCounts.Length && i < UpstreamMetrics.DurationBuckets.Length; i++)
                    sb.Append(hist).Append("_bucket{provider=\"").Append(Escape(h.Provider))
                        .Append("\",le=\"").Append(UpstreamMetrics.DurationBuckets[i].ToString("0.###", CultureInfo.InvariantCulture))
                        .Append("\"} ").Append(h.BucketCounts[i]).Append('\n');
                sb.Append(hist).Append("_bucket{provider=\"").Append(Escape(h.Provider))
                    .Append("\",le=\"+Inf\"} ").Append(h.Count).Append('\n');
                sb.Append(hist).Append("_sum{provider=\"").Append(Escape(h.Provider))
                    .Append("\"} ").Append(h.Sum.ToString("0.######", CultureInfo.InvariantCulture)).Append('\n');
                sb.Append(hist).Append("_count{provider=\"").Append(Escape(h.Provider))
                    .Append("\"} ").Append(h.Count).Append('\n');
            }

            if (upstream.RateLimitRemaining is { } remaining)
                Gauge(sb, "metacache_tmdb_rate_limit_remaining", "TMDB API requests remaining in the current rate-limit window (X-RateLimit-Remaining), from the latest response.", remaining);
            if (upstream.RateLimitLimit is { } limit)
                Gauge(sb, "metacache_tmdb_rate_limit_limit", "TMDB API rate-limit window size (X-RateLimit-Limit), from the latest response.", limit);
            foreach ((string provider, long count) in upstream.RateLimitedCounts)
                Counter(sb, "metacache_upstream_rate_limited_total", "Upstream 429 (Too Many Requests) responses received, by provider.", count, ("provider", provider));
        }

        return sb.ToString();
    }

    private static void Counter(StringBuilder sb, string name, string help, long value, (string, string)? label = null) =>
        Emit(sb, name, help, "counter", value, label);

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
