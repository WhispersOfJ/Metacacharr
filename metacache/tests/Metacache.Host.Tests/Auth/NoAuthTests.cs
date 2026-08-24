using System.Net;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests.Auth;

/// <summary>
/// Verifies that when no API key is configured, all endpoints are accessible
/// without authentication (backward compatible behavior).
/// </summary>
public class NoAuthTests : IDisposable
{
    private readonly string _imageDir;
    private readonly FakeUpstream _upstream = new();
    private readonly WebApplicationFactory<Program> _factory;

    public NoAuthTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-noauth-{Guid.NewGuid():N}");
        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("Metacache:DataPath", ":memory:");
                builder.UseSetting("Metacache:Images:Directory", _imageDir);
                builder.UseSetting("Metacache:Tmdb:ApiKey", "test-api-key");
                // No Auth:ApiKey set — auth should be disabled
                builder.ConfigureTestServices(services => services.AddSingleton<IUpstreamHttp>(_ => _upstream));
            });
    }

    public void Dispose()
    {
        _factory.Dispose();
        if (Directory.Exists(_imageDir))
            Directory.Delete(_imageDir, true);
    }

    [Fact]
    public async Task Admin_overrides_accessible_without_token_when_no_key_configured()
    {
        var client = _factory.CreateClient();
        var resp = await client.GetAsync("/admin/overrides");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
    }

    [Fact]
    public async Task Warm_all_accessible_without_token_when_no_key_configured()
    {
        var client = _factory.CreateClient();
        var resp = await client.PostAsync("/warm/all", null);
        // Should get past auth — may return 200/409/500 but not 401
        Assert.NotEqual(HttpStatusCode.Unauthorized, resp.StatusCode);
    }
}
