using System.Net;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests;

public class ImageEndpointsTests : IDisposable
{
    private readonly string _imageDir;
    private readonly FakeUpstream _upstream;
    private readonly WebApplicationFactory<Program> _factory;

    public ImageEndpointsTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-img-{Guid.NewGuid():N}");
        _upstream = new FakeUpstream();
        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("Metacache:DataPath", ":memory:");
                builder.UseSetting("Metacache:Images:Directory", _imageDir);
                builder.ConfigureTestServices(services => services.AddSingleton<IUpstreamHttp>(_upstream));
            });
    }

    public void Dispose()
    {
        _factory.Dispose();
        if (Directory.Exists(_imageDir))
            Directory.Delete(_imageDir, recursive: true);
    }

    private const string Url = "https://image.tmdb.org/t/p/original/poster.jpg";

    [Fact]
    public async Task Serves_seeded_image_with_content_type()
    {
        _upstream.Handler = _ => new UpstreamResponse(200, TestBytes.Of("fake-jpeg-bytes"), "image/jpeg", null, null, null);
        await _factory.Services.GetRequiredService<ImageCache>().GetOrFetchAsync(Url); // seed

        var response = await _factory.CreateClient().GetAsync(ImageCache.RewriteToLocalPath(Url));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("image/jpeg", response.Content.Headers.ContentType!.MediaType);
        Assert.Equal("fake-jpeg-bytes", await response.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Stored_url_refetches_when_the_file_is_missing()
    {
        const string url = "https://image.tmdb.org/t/p/original/lazy.png";
        _upstream.Handler = _ => new UpstreamResponse(200, TestBytes.Of("lazy"), "image/png", null, null, null);

        ImageResult seeded = await _factory.Services.GetRequiredService<ImageCache>().GetOrFetchAsync(url);
        File.Delete(seeded.Path); // simulate a lost file; the urls row remains

        var response = await _factory.CreateClient().GetAsync(ImageCache.RewriteToLocalPath(url));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("image/png", response.Content.Headers.ContentType!.MediaType);
        Assert.Equal("lazy", await response.Content.ReadAsStringAsync());
        Assert.Equal(2, _upstream.Requests.Count); // seed fetch + one refetch
    }

    [Fact]
    public async Task Unknown_hash_returns_404()
    {
        string hash = UpstreamCache.ComputeKey("https://image.tmdb.org/t/p/original/never-seen.jpg");

        var response = await _factory.CreateClient().GetAsync($"/img/{hash}");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Invalid_hash_returns_404()
    {
        var response = await _factory.CreateClient().GetAsync("/img/not-a-real-hash");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }
}
