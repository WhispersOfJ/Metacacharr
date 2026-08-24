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
