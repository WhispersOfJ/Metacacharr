using System.Net;
using System.Net.Http.Json;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests.Auth;

/// <summary>
/// Integration tests for the bearer-token auth middleware on protected endpoints.
/// </summary>
public class AuthMiddlewareTests : IDisposable
{
    private readonly string _imageDir;
    private readonly FakeUpstream _upstream = new();
    private readonly WebApplicationFactory<Program> _factory;

    public AuthMiddlewareTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-auth-{Guid.NewGuid():N}");
        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("Metacache:DataPath", ":memory:");
                builder.UseSetting("Metacache:Images:Directory", _imageDir);
                builder.UseSetting("Metacache:Tmdb:ApiKey", "test-api-key");
                builder.UseSetting("Metacache:Auth:ApiKey", "super-secret-token");
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

    private static HttpRequestMessage Protected(string path, string method = "GET", string? body = null)
    {
        var msg = new HttpRequestMessage(new HttpMethod(method), path);
        if (body is not null)
            msg.Content = new StringContent(body, System.Text.Encoding.UTF8, "application/json");
        return msg;
    }

    // --- 401 cases ---

    [Fact]
    public async Task Admin_endpoint_without_token_returns_401()
    {
        var resp = await Client().GetAsync("/admin/overrides");
        Assert.Equal(HttpStatusCode.Unauthorized, resp.StatusCode);
        Assert.Equal("Bearer", resp.Headers.WwwAuthenticate.FirstOrDefault()?.Scheme);
    }

    [Fact]
    public async Task Webhook_endpoint_without_token_returns_401()
    {
        var resp = await Client().PostAsync("/webhook/radarr",
            new StringContent("{}", System.Text.Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.Unauthorized, resp.StatusCode);
    }

    [Fact]
    public async Task Post_warm_endpoint_without_token_returns_401()
    {
        var resp = await Client().PostAsync("/warm/all", null);
        Assert.Equal(HttpStatusCode.Unauthorized, resp.StatusCode);
    }

    [Fact]
    public async Task Wrong_token_returns_401()
    {
        var msg = Protected("/admin/overrides");
        msg.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", "wrong-token");
        var resp = await Client().SendAsync(msg);
        Assert.Equal(HttpStatusCode.Unauthorized, resp.StatusCode);
    }

    [Fact]
    public async Task X_API_Key_header_with_wrong_key_returns_401()
    {
        var msg = Protected("/admin/overrides");
        msg.Headers.Add("X-API-Key", "wrong-key");
        var resp = await Client().SendAsync(msg);
        Assert.Equal(HttpStatusCode.Unauthorized, resp.StatusCode);
    }

    // --- 200 cases (authenticated) ---

    [Fact]
    public async Task Admin_endpoint_with_valid_bearer_token_returns_200()
    {
        var msg = Protected("/admin/overrides");
        msg.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", "super-secret-token");
        var resp = await Client().SendAsync(msg);
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
    }

    [Fact]
    public async Task Admin_endpoint_with_valid_X_API_Key_returns_200()
    {
        var msg = Protected("/admin/overrides");
        msg.Headers.Add("X-API-Key", "super-secret-token");
        var resp = await Client().SendAsync(msg);
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
    }

    [Fact]
    public async Task Webhook_endpoint_with_valid_token_returns_409_or_400()
    {
        // Radarr webhook with valid token — should get past auth (409 = already warm, or 400 = bad payload)
        var msg = Protected("/webhook/radarr", "POST", "{}");
        msg.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", "super-secret-token");
        var resp = await Client().SendAsync(msg);
        // Valid token gets past auth; the webhook may return 200/400/409 depending on payload
        Assert.True(resp.StatusCode is not HttpStatusCode.Unauthorized,
            $"Auth should have passed, got {resp.StatusCode}");
    }

    // --- Unprotected routes pass through ---

    [Fact]
    public async Task Healthz_always_passes_without_token()
    {
        var resp = await Client().GetAsync("/healthz");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
    }

    [Fact]
    public async Task Movie_provider_always_passes_without_token()
    {
        var resp = await Client().GetAsync("/movie");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
    }

    [Fact]
    public async Task Cache_stats_always_passes_without_token()
    {
        var resp = await Client().GetAsync("/cache/stats");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
    }

    [Fact]
    public async Task Warm_status_always_passes_without_token()
    {
        var resp = await Client().GetAsync("/warm/status");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
    }

    [Fact]
    public async Task Metrics_always_passes_without_token()
    {
        var resp = await Client().GetAsync("/metrics");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
    }
}
