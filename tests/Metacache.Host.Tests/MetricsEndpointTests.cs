using System.Net.Http.Json;
using System.Text.Json;
using Metacache.Core.Cache;

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
