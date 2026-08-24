using System.Net.Http.Json;
using System.Text.Json;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;

namespace Metacache.Host.Tests;

public class MetricsEndpointTests : ProviderEndpointTestBase
{
    private static JsonElement Metrics(JsonDocument doc) => doc.RootElement;

    private async Task<JsonDocument> GetMetricsAsync() =>
        JsonDocument.Parse(await Client.GetStringAsync("/metrics"));

    [Fact]
    public async Task Metrics_start_empty()
    {
        using JsonDocument doc = await GetMetricsAsync();
        JsonElement root = Metrics(doc);

        Assert.Equal(0, root.GetProperty("hitRate").GetDouble());
        Assert.Equal(0, root.GetProperty("requests").GetInt32());
        Assert.Equal(0, root.GetProperty("hits").GetInt32());
        Assert.Empty(root.GetProperty("itemsByKind").EnumerateObject());
        Assert.Equal(0, root.GetProperty("images").GetProperty("files").GetInt32());
        Assert.Equal(JsonValueKind.Null, root.GetProperty("dbBytes").ValueKind); // :memory: has no file
    }

    [Fact]
    public async Task Dashboard_is_served_as_a_self_contained_html_page()
    {
        var response = await Client.GetAsync("/dashboard");

        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("text/html", response.Content.Headers.ContentType!.MediaType);
        string html = await response.Content.ReadAsStringAsync();
        Assert.Contains("Metacache", html);
        Assert.Contains("hitRate", html);      // polls /metrics by name
        Assert.Contains("/metrics", html);     // and fetches it live
        Assert.Contains("scrapeHistory", html); // overlays the Prometheus scrape record
        Assert.Contains("<script>", html);     // self-contained, no external assets
    }

    [Fact]
    public async Task Prometheus_metrics_are_served_in_text_format()
    {
        await Client.GetAsync("/library/metadata/tmdb-movie-105"); // three upstream misses

        var response = await Client.GetAsync("/metrics/prometheus");
        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("text/plain", response.Content.Headers.ContentType!.MediaType);
        Assert.Contains("version=0.0.4", response.Content.Headers.ContentType!.ToString());
        string body = await response.Content.ReadAsStringAsync();

        // HELP/TYPE lines and the _total counter convention.
        Assert.Contains("# HELP metacache_cache_requests_total", body);
        Assert.Contains("# TYPE metacache_cache_requests_total counter", body);
        Assert.Contains("# TYPE metacache_cache_hit_ratio gauge", body);
        Assert.Contains("metacache_cache_requests_total ", body);
        Assert.Contains("metacache_cache_hits_total 0", body);
        Assert.Contains("metacache_cache_misses_total ", body);
        Assert.Contains("metacache_cache_hit_ratio 0", body);

        // No items warmed yet → the kind gauge has no instances (empty series are omitted).
        Assert.DoesNotContain("metacache_items_by_kind", body);

        // Every metric line is a well-formed number.
        foreach (string line in body.Split('\n'))
        {
            if (line.Length == 0 || line.StartsWith('#'))
                continue;
            string value = line[(line.LastIndexOf(' ') + 1)..];
            Assert.True(double.TryParse(value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out _),
                $"not a number: {line}");
        }

        // A repeat fetch is served from cache: hits become the first-run request count.
        await Client.GetAsync("/library/metadata/tmdb-movie-105");
        string after = await Client.GetStringAsync("/metrics/prometheus");
        Assert.DoesNotContain("metacache_cache_hits_total 0", after);
        Assert.Contains("metacache_cache_hit_ratio 0.5", after);

        // Warm one movie via the webhook → the kind label appears with its count.
        await Client.PostAsync("/webhook/radarr",
            JsonBody("""{"eventType":"Download","movie":{"id":1,"tmdbId":105,"title":"Back to the Future"}}"""));
        string warmed = await Client.GetStringAsync("/metrics/prometheus");
        Assert.Contains("metacache_items_by_kind{kind=\"movie\"} 1", warmed);

        // :memory: store has no DB file — the metric is omitted, not NaN.
        Assert.DoesNotContain("metacache_db_bytes", body);
    }

    [Fact]
    public async Task Prometheus_metrics_include_warm_run_status()
    {
        // Before any warm: running gauge present, no last-run series yet.
        string initial = await Client.GetStringAsync("/metrics/prometheus");
        Assert.Contains("metacache_warm_running 0", initial);
        Assert.DoesNotContain("metacache_warm_last_items", initial);
        Assert.DoesNotContain("metacache_warm_last_timestamp_seconds", initial);

        // A webhook warm publishes the run: per-source gauges + completion time.
        var warm = await Client.PostAsync("/webhook/radarr",
            JsonBody("""{"eventType":"Download","movie":{"id":1,"tmdbId":105,"title":"Back to the Future"}}"""));
        Assert.Equal(System.Net.HttpStatusCode.OK, warm.StatusCode);

        string after = await Client.GetStringAsync("/metrics/prometheus");
        Assert.Contains("metacache_warm_running 0", after);
        Assert.Contains("metacache_warm_last_items{source=\"movie\"} 1", after);
        Assert.Contains("metacache_warm_last_errors{source=\"movie\"} 0", after);
        Assert.Contains("metacache_warm_last_success{source=\"movie\"} 1", after);
        Assert.Contains("# TYPE metacache_warm_last_items gauge", after);

        string? timestampLine = after.Split('\n').FirstOrDefault(l => l.StartsWith("metacache_warm_last_timestamp_seconds ", StringComparison.Ordinal));
        Assert.NotNull(timestampLine);
        long epoch = long.Parse(timestampLine!["metacache_warm_last_timestamp_seconds ".Length..]);
        Assert.True(epoch > 0, "warm completion timestamp should be a real unix time");
    }

    [Fact]
    public async Task Prometheus_metrics_include_upstream_duration_histograms_and_rate_limit()
    {
        // Serve the movie fetch path with TMDB rate-limit headers so the gauge lands.
        Upstream.Handler = request =>
        {
            string path = request.Url.AbsolutePath;
            string body = path.EndsWith("/movie/105/credits", StringComparison.Ordinal) ? TmdbTestData.MovieCreditsJson
                : path.EndsWith("/movie/105/release_dates", StringComparison.Ordinal) ? TmdbTestData.ReleaseDatesJson
                : path.Contains("/movie/105", StringComparison.Ordinal) ? TmdbTestData.Movie105Json
                : throw new InvalidOperationException($"Unexpected upstream request: {request.Url}");
            return new UpstreamResponse(200, TestBytes.Of(body), "application/json", null, null, null,
                new Dictionary<string, string>
                {
                    ["X-RateLimit-Remaining"] = "39",
                    ["X-RateLimit-Limit"] = "40"
                });
        };

        await Client.GetAsync("/library/metadata/tmdb-movie-105"); // 3 upstream calls
        string body2 = await Client.GetStringAsync("/metrics/prometheus");

        // Histogram: count/sum per provider, +Inf bucket equals the total.
        Assert.Contains("# TYPE metacache_upstream_request_duration_seconds histogram", body2);
        string countLine = body2.Split('\n')
            .First(l => l.StartsWith("metacache_upstream_request_duration_seconds_count{provider=\"tmdb\"}", StringComparison.Ordinal));
        long count = long.Parse(countLine[(countLine.LastIndexOf(' ') + 1)..]);
        Assert.True(count >= 3, $"expected >= 3 tmdb observations, got {count}");
        string infLine = body2.Split('\n')
            .First(l => l.Contains("le=\"+Inf\"}", StringComparison.Ordinal) && l.Contains("provider=\"tmdb\"", StringComparison.Ordinal));
        Assert.Equal(count, long.Parse(infLine[(infLine.LastIndexOf(' ') + 1)..]));
        Assert.Contains("metacache_upstream_request_duration_seconds_sum{provider=\"tmdb\"}", body2);

        // Rate-limit gauges from the response headers.
        Assert.Contains("# TYPE metacache_tmdb_rate_limit_remaining gauge", body2);
        Assert.Contains("metacache_tmdb_rate_limit_remaining 39", body2);
        Assert.Contains("metacache_tmdb_rate_limit_limit 40", body2);
    }

    [Fact]
    public async Task Prometheus_metrics_count_rate_limited_responses()
    {
        Upstream.Handler = _ => new UpstreamResponse(429, TestBytes.Of("rate limited"), "text/plain", null, null, null);

        // The metadata call fails with 429; the counter still registers per provider.
        await Client.GetAsync("/library/metadata/tmdb-movie-105");

        string body = await Client.GetStringAsync("/metrics/prometheus");
        Assert.Contains("# TYPE metacache_upstream_rate_limited_total counter", body);
        string counterLine = body.Split('\n')
            .First(l => l.StartsWith("metacache_upstream_rate_limited_total", StringComparison.Ordinal));
        Assert.Contains("provider=\"tmdb\"}", counterLine);
        long count = long.Parse(counterLine[(counterLine.LastIndexOf(' ') + 1)..]);
        Assert.True(count >= 1, $"expected >= 1 rate-limited response, got {count}");
    }

    [Fact]
    public async Task Prometheus_scrapes_are_recorded_for_the_dashboard_overlay()
    {
        await Client.GetAsync("/library/metadata/tmdb-movie-105"); // 3 upstream misses
        await Client.GetStringAsync("/metrics/prometheus");        // scrape 1: hit rate 0

        await Client.GetAsync("/library/metadata/tmdb-movie-105"); // 3 cache hits
        await Client.GetStringAsync("/metrics/prometheus");        // scrape 2: hit rate 0.5

        using JsonDocument doc = JsonDocument.Parse(await Client.GetStringAsync("/metrics"));
        JsonElement scrapes = doc.RootElement.GetProperty("scrapeHistory");
        Assert.Equal(2, scrapes.GetArrayLength());

        JsonElement first = scrapes[0];
        Assert.Equal(0, first.GetProperty("hitRate").GetDouble());
        Assert.Equal(0, first.GetProperty("hits").GetInt32());
        Assert.Equal(3, first.GetProperty("requests").GetInt32());
        Assert.True(first.GetProperty("unixSeconds").GetInt64() > 0);

        JsonElement second = scrapes[1];
        Assert.Equal(0.5, second.GetProperty("hitRate").GetDouble(), precision: 2);
        Assert.Equal(3, second.GetProperty("hits").GetInt32());
        Assert.Equal(6, second.GetProperty("requests").GetInt32());
        Assert.True(second.GetProperty("unixSeconds").GetInt64() >= first.GetProperty("unixSeconds").GetInt64());
    }

    [Fact]
    public async Task Metrics_reflect_cache_hits_and_disk_usage()
    {
        // First metadata fetch: all upstream misses.
        await Client.GetAsync("/library/metadata/tmdb-movie-105");
        using (JsonDocument doc = await GetMetricsAsync())
        {
            JsonElement root = Metrics(doc);
            Assert.True(root.GetProperty("requests").GetInt32() >= 3); // movie + credits + release dates
            Assert.Equal(0, root.GetProperty("hits").GetInt32());
            Assert.Equal(0, root.GetProperty("hitRate").GetDouble());
            Assert.True(root.GetProperty("upstreamEntries").GetInt32() >= 3);
        }

        // Same fetch again: served from cache — hits should equal the requests from run 1.
        await Client.GetAsync("/library/metadata/tmdb-movie-105");
        using (JsonDocument doc = await GetMetricsAsync())
        {
            JsonElement root = Metrics(doc);
            int requests = root.GetProperty("requests").GetInt32();
            int hits = root.GetProperty("hits").GetInt32();
            Assert.Equal(requests / 2, hits);
            Assert.Equal(0.5, root.GetProperty("hitRate").GetDouble(), precision: 2);
        }

        // Pull an actual image through /img → disk usage goes non-zero.
        string hash = ImageCache.RewriteToLocalPath("https://image.tmdb.org/t/p/original/bttf-poster.jpg");
        var imageResponse = await Client.GetAsync($"/img/{hash[5..]}");
        Assert.Equal(System.Net.HttpStatusCode.OK, imageResponse.StatusCode);
        using (JsonDocument doc = await GetMetricsAsync())
        {
            JsonElement root = Metrics(doc);
            Assert.True(root.GetProperty("images").GetProperty("files").GetInt32() >= 1);
            Assert.True(root.GetProperty("images").GetProperty("bytes").GetInt64() > 0);
        }
    }
}
