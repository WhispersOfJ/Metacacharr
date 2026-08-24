using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests;

/// <summary>
/// Integration tests for the admin dashboard endpoints: per-item inspection,
/// upstream entry browsing, and selective purge.
/// </summary>
public class AdminEndpointsTests : IDisposable
{
    private readonly string _imageDir;
    private readonly FakeUpstream _upstream = new();
    private readonly WebApplicationFactory<Program> _factory;

    public AdminEndpointsTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-admin-{Guid.NewGuid():N}");
        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("Metacache:DataPath", ":memory:");
                builder.UseSetting("Metacache:Images:Directory", _imageDir);
                builder.UseSetting("Metacache:Tmdb:ApiKey", "test-api-key");
                builder.ConfigureTestServices(services => services.AddSingleton<IUpstreamHttp>(_ => _upstream));
            });
    }

    public void Dispose()
    {
        _factory.Dispose();
        if (Directory.Exists(_imageDir))
            Directory.Delete(_imageDir, true);
    }

    private HttpClient Client() => _factory.CreateClient();

    [Fact]
    public async Task Admin_items_search_returns_empty_initially()
    {
        var resp = await Client().GetAsync("/admin/items");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var json = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(0, json.GetProperty("total").GetInt32());
    }

    [Fact]
    public async Task Admin_items_search_validates_fresh_parameter()
    {
        var resp = await Client().GetAsync("/admin/items?fresh=maybe");
        Assert.Equal(HttpStatusCode.BadRequest, resp.StatusCode);
    }

    [Fact]
    public async Task Admin_items_search_validates_limit()
    {
        var resp = await Client().GetAsync("/admin/items?limit=abc");
        Assert.Equal(HttpStatusCode.BadRequest, resp.StatusCode);
    }

    [Fact]
    public async Task Admin_items_search_clamps_limit()
    {
        var resp = await Client().GetAsync("/admin/items?limit=9999");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var json = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.GetProperty("total").GetInt32() >= 0);
    }

    [Fact]
    public async Task Admin_upstream_returns_stats()
    {
        var resp = await Client().GetAsync("/admin/upstream");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var json = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.TryGetProperty("stats", out _));
        Assert.True(json.TryGetProperty("evictionCandidates", out _));
    }

    [Fact]
    public async Task Admin_database_returns_info()
    {
        var resp = await Client().GetAsync("/admin/database");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var json = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.TryGetProperty("upstreamEntries", out _));
        Assert.True(json.TryGetProperty("itemEntries", out _));
        Assert.True(json.TryGetProperty("imageBytes", out _));
    }

    [Fact]
    public async Task Admin_purge_selective_removes_expired()
    {
        var resp = await Client().PostAsync("/admin/purge/selective",
            new StringContent("{\"expired\":true}", System.Text.Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var json = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.GetProperty("removed").GetInt32() >= 0);
    }

    [Fact]
    public async Task Admin_purge_selective_empty_body_works()
    {
        var resp = await Client().PostAsync("/admin/purge/selective",
            new StringContent("{}", System.Text.Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var json = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(0, json.GetProperty("removed").GetInt32());
    }

    [Fact]
    public async Task Admin_items_item_not_found_returns_404()
    {
        var resp = await Client().GetAsync("/admin/items/nonexistent-id");
        Assert.Equal(HttpStatusCode.NotFound, resp.StatusCode);
    }
}
