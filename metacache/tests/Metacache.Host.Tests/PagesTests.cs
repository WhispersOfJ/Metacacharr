using System.Net;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests;

/// <summary>
/// Tests for the 10 UI pages and warm progress endpoint.
/// </summary>
public class PagesTests : IDisposable
{
    private readonly string _imageDir;
    private readonly FakeUpstream _upstream = new();
    private readonly WebApplicationFactory<Program> _factory;

    public PagesTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-pages-{Guid.NewGuid():N}");
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

    [Theory]
    [InlineData("/ui/setup")]
    [InlineData("/ui/health")]
    [InlineData("/ui/freshness")]
    [InlineData("/ui/register")]
    [InlineData("/ui/matches")]
    [InlineData("/ui/guid")]
    [InlineData("/ui/overrides")]
    [InlineData("/ui/warm-calendar")]
    [InlineData("/ui/warm-progress")]
    [InlineData("/ui/cache-diff")]
    public async Task All_pages_return_200_with_html(string path)
    {
        var resp = await Client().GetAsync(path);
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var html = await resp.Content.ReadAsStringAsync();
        Assert.Contains("<html", html);
        Assert.Contains("</html>", html);
    }

    [Fact]
    public async Task Warm_progress_returns_json()
    {
        var resp = await Client().GetAsync("/warm/progress");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var json = await System.Text.Json.JsonDocument.ParseAsync(await resp.Content.ReadAsStreamAsync());
        Assert.True(json.RootElement.TryGetProperty("isRunning", out _) ||
                     json.RootElement.TryGetProperty("processedItems", out _));
    }
}
