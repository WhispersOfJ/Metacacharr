using Metacache.Core.Cache;
using Microsoft.Extensions.Logging.Abstractions;

namespace Metacache.Host.Tests.Cache;

public class ImageCacheTests : IDisposable
{
    private sealed class Fixture : IDisposable
    {
        public FakeClock Clock { get; } = new(DateTimeOffset.Parse("2026-08-24T00:00:00+00:00"));
        public FakeUpstream Upstream { get; } = new();
        public CacheStore Store { get; }
        public ImageStore ImageStore { get; }
        public ImageCache Cache { get; }
        public string ImageDir { get; }

        public Fixture(long maxFileBytes = 1024 * 1024, long maxTotalBytes = 10L * 1024 * 1024)
        {
            ImageDir = Path.Combine(Path.GetTempPath(), $"metacache-img-{Guid.NewGuid():N}");
            Store = new CacheStore(":memory:", Clock);
            ImageStore = new ImageStore(ImageDir, maxFileBytes);
            Cache = new ImageCache(Store, ImageStore, Upstream, new SingleFlight(), Clock,
                NullLogger<ImageCache>.Instance, maxTotalBytes);
        }

        public void Dispose()
        {
            Store.Dispose();
            if (Directory.Exists(ImageDir))
                Directory.Delete(ImageDir, recursive: true);
        }
    }

    private const string Url = "https://image.tmdb.org/t/p/original/poster.jpg";

    private static UpstreamResponse Jpeg(string body) =>
        new(200, TestBytes.Of(body), "image/jpeg", null, null, null);

    public void Dispose() { } // fixtures are per-test

    [Fact]
    public async Task Miss_fetches_stores_and_serves_from_disk()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Jpeg("fake-jpeg");

        ImageResult first = await f.Cache.GetOrFetchAsync(Url);
        ImageResult second = await f.Cache.GetOrFetchAsync(Url);

        Assert.Equal(ImageSource.Upstream, first.Source);
        Assert.Equal(ImageSource.Cache, second.Source);
        Assert.Equal("fake-jpeg", File.ReadAllText(first.Path));
        Assert.Equal("image/jpeg", first.ContentType);
        Assert.Single(f.Upstream.Requests);

        string hash = UpstreamCache.ComputeKey(Url);
        Assert.NotNull(f.Store.GetUrl(hash));
        Assert.True(f.ImageStore.Exists(hash));
    }

    [Fact]
    public async Task Concurrent_misses_cause_single_upstream_call()
    {
        using var f = new Fixture();
        int calls = 0;
        f.Upstream.Handler = _ =>
        {
            Interlocked.Increment(ref calls);
            Thread.Sleep(30);
            return Jpeg("img");
        };

        ImageResult[] results = await Task.WhenAll(
            Enumerable.Range(0, 8).Select(_ => f.Cache.GetOrFetchAsync(Url)));

        Assert.Equal(8, results.Length);
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task Over_cap_image_throws_and_leaves_no_trace()
    {
        using var f = new Fixture(maxFileBytes: 4);
        f.Upstream.Handler = _ => new UpstreamResponse(200, [1, 2, 3, 4, 5], "image/jpeg", null, null, null);

        ImageTooLargeException ex = await Assert.ThrowsAsync<ImageTooLargeException>(
            () => f.Cache.GetOrFetchAsync(Url));

        Assert.Equal(5, ex.Size);
        Assert.Null(f.Store.GetUrl(UpstreamCache.ComputeKey(Url)));
        Assert.False(f.ImageStore.Exists(UpstreamCache.ComputeKey(Url)));
    }

    [Fact]
    public async Task Total_cap_evicts_oldest_first()
    {
        using var f = new Fixture(maxTotalBytes: 100);
        f.Upstream.Handler = _ => new UpstreamResponse(200, Enumerable.Repeat((byte)1, 40).ToArray(), "image/jpeg", null, null, null);

        await f.Cache.GetOrFetchAsync("https://x/1.jpg");
        f.Clock.UtcNow = f.Clock.UtcNow.AddMinutes(1);
        await f.Cache.GetOrFetchAsync("https://x/2.jpg");
        f.Clock.UtcNow = f.Clock.UtcNow.AddMinutes(1);
        await f.Cache.GetOrFetchAsync("https://x/3.jpg");

        Assert.True(f.Store.SumUrlBytes() <= 100, "total should be back under the cap");
        Assert.Null(f.Store.GetUrl(UpstreamCache.ComputeKey("https://x/1.jpg")));   // oldest evicted
        Assert.False(f.ImageStore.Exists(UpstreamCache.ComputeKey("https://x/1.jpg")));
        Assert.NotNull(f.Store.GetUrl(UpstreamCache.ComputeKey("https://x/2.jpg")));
        Assert.NotNull(f.Store.GetUrl(UpstreamCache.ComputeKey("https://x/3.jpg")));
    }

    [Fact]
    public async Task NotFound_upstream_throws_and_stores_nothing()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(404, [], null, null, null, null);

        UpstreamException ex = await Assert.ThrowsAsync<UpstreamException>(() => f.Cache.GetOrFetchAsync(Url));

        Assert.Equal(404, ex.StatusCode);
        Assert.Null(f.Store.GetUrl(UpstreamCache.ComputeKey(Url)));
    }

    [Fact]
    public async Task GetByHashAsync_serves_a_stored_url_and_returns_null_for_unknown()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Jpeg("stored");

        await f.Cache.GetOrFetchAsync(Url);
        string hash = UpstreamCache.ComputeKey(Url);

        ImageResult? byHash = await f.Cache.GetByHashAsync(hash);
        Assert.NotNull(byHash);
        Assert.Equal("stored", File.ReadAllText(byHash!.Path));

        Assert.Null(await f.Cache.GetByHashAsync(UpstreamCache.ComputeKey("https://x/unknown.jpg")));
    }

    [Fact]
    public void RewriteToLocalPath_is_deterministic_and_unique()
    {
        string a = ImageCache.RewriteToLocalPath(Url);
        string b = ImageCache.RewriteToLocalPath(Url);
        string c = ImageCache.RewriteToLocalPath("https://image.tmdb.org/t/p/original/other.jpg");

        Assert.Equal(a, b);
        Assert.StartsWith("/img/", a);
        Assert.NotEqual(a, c);
    }
}
