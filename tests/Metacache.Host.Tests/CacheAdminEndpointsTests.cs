using System.Net;
using System.Net.Http.Json;
using Metacache.Core.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests;

public class CacheAdminEndpointsTests : IDisposable
{
    private static readonly DateTimeOffset Now = DateTimeOffset.UtcNow;

    /// <summary>Each test gets its own app instance with an isolated in-memory store.</summary>
    private readonly WebApplicationFactory<Program> _factory;

    public CacheAdminEndpointsTests()
    {
        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder => builder.UseSetting("Metacache:DataPath", ":memory:"));
    }

    public void Dispose() => _factory.Dispose();

    private HttpClient Client => _factory.CreateClient();

    private CacheStore Store => _factory.Services.GetRequiredService<CacheStore>();

    [Fact]
    public async Task Stats_returns_zeroes_for_an_empty_cache()
    {
        CacheStats? stats = await Client.GetFromJsonAsync<CacheStats>("/cache/stats");

        Assert.NotNull(stats);
        Assert.Equal(0, stats.UpstreamEntries);
        Assert.Equal(0, stats.UpstreamBytes);
        Assert.Equal(0, stats.ItemEntries);
        Assert.Equal(0, stats.UrlEntries);
    }

    [Fact]
    public async Task Stats_reflect_seeded_rows()
    {
        Store.PutUpstream(new CachedUpstreamRow("k1", "https://x/1", 200, "application/json",
            "hello"u8.ToArray(), Now, Now.AddHours(1), null, null, Hits: 0));
        Store.PutUpstream(new CachedUpstreamRow("k2", "https://x/2", 200, "application/json",
            "world"u8.ToArray(), Now, Now.AddHours(1), null, null, Hits: 0));
        Store.PutItem(new CachedItem("i1", "movie", "tmdb", "1", "en-US", "{}", Now, Now.AddHours(1), null));
        Store.PutUrl(new CachedUrl("u1", "https://img/1.jpg", "img/1.jpg", 42, Now));

        var response = await Client.GetAsync("/cache/stats");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var raw = await response.Content.ReadAsStringAsync();
        Assert.Contains("\"upstreamEntries\"", raw); // admin JSON is camelCase

        CacheStats? stats = await response.Content.ReadFromJsonAsync<CacheStats>();
        Assert.Equal(2, stats!.UpstreamEntries);
        Assert.Equal(10, stats.UpstreamBytes); // "hello" + "world"
        Assert.Equal(1, stats.ItemEntries);
        Assert.Equal(1, stats.UrlEntries);
    }

    [Fact]
    public async Task Purge_removes_expired_rows_and_reports_count()
    {
        Store.PutUpstream(new CachedUpstreamRow("expired", "https://x/expired", 200, null,
            "x"u8.ToArray(), Now.AddHours(-2), Now.AddHours(-1), null, null, Hits: 0));
        Store.PutUpstream(new CachedUpstreamRow("fresh", "https://x/fresh", 200, null,
            "y"u8.ToArray(), Now.AddMinutes(-1), Now.AddHours(1), null, null, Hits: 0));
        Store.PutItem(new CachedItem("expired-item", "movie", "tmdb", "1", "en-US", "{}",
            Now.AddHours(-2), Now.AddHours(-1), null));

        var response = await Client.PostAsync("/cache/purge", null);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var result = await response.Content.ReadFromJsonAsync<PurgeResult>();
        Assert.Equal(2, result!.Removed);
        Assert.NotNull(Store.GetUpstream("fresh"));
        Assert.Null(Store.GetUpstream("expired"));
    }

    [Fact]
    public async Task Purge_returns_zero_when_nothing_is_expired()
    {
        var response = await Client.PostAsync("/cache/purge", null);

        var result = await response.Content.ReadFromJsonAsync<PurgeResult>();
        Assert.Equal(0, result!.Removed);
    }

    private sealed record PurgeResult(int Removed);
}
