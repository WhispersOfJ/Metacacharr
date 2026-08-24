using Metacache.Core.Cache;
using Microsoft.Extensions.Logging.Abstractions;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.Formats.Jpeg;
using SixLabors.ImageSharp.PixelFormats;

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
            Cache = new ImageCache(Store, ImageStore, Upstream, new SingleFlight(), Clock, new UpstreamMetrics(),
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
    public async Task Registered_url_is_fetchable_on_first_request_without_clobbering_paths()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Jpeg("registered");
        string hash = UpstreamCache.ComputeKey(Url);

        f.Cache.RegisterUrl(Url);
        CachedUrl? before = f.Store.GetUrl(hash);
        Assert.NotNull(before);
        Assert.False(f.ImageStore.Exists(hash)); // registered, not fetched

        // Row exists but no file yet → GetByHashAsync (the /img endpoint path) fetches + stores.
        ImageResult? result = await f.Cache.GetByHashAsync(hash);
        Assert.NotNull(result);
        Assert.Equal("registered", File.ReadAllText(result!.Path));
        Assert.Equal(ImageSource.Upstream, result.Source);
        Assert.Single(f.Upstream.Requests);

        // Registering again must not clobber the stored file path.
        f.Cache.RegisterUrl(Url);
        Assert.Equal(result.Path, f.Store.GetUrl(hash)!.Path);
        Assert.True(f.ImageStore.Exists(hash));
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

    // ---- sized variants (§21) ----

    [Fact]
    public async Task Variant_resizes_caches_and_serves_from_disk()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(200, MakeJpeg(400, 200), "image/jpeg", null, null, null);
        string hash = UpstreamCache.ComputeKey(Url);
        await f.Cache.GetOrFetchAsync(Url); // warm the original

        ImageResult variant = (await f.Cache.GetVariantAsync(hash, 185))!;

        Assert.True(f.ImageStore.VariantExists(hash, 185));
        Assert.Equal("image/jpeg", variant.ContentType);
        using (Image decoded = Image.Load(variant.Path))
        {
            Assert.Equal(185, Math.Max(decoded.Width, decoded.Height)); // longest side bound
            Assert.Equal(92, Math.Min(decoded.Width, decoded.Height)); // 2:1 aspect preserved
        }

        // Second call serves the cached variant without resizing again.
        ImageResult cached = (await f.Cache.GetVariantAsync(hash, 185))!;
        Assert.Equal(variant.Path, cached.Path);
        Assert.Single(f.Upstream.Requests); // original fetched once; variant is local work
    }

    [Fact]
    public async Task Variant_smaller_than_the_original_serves_the_original()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(200, MakeJpeg(64, 32), "image/jpeg", null, null, null);
        string hash = UpstreamCache.ComputeKey(Url);
        ImageResult original = await f.Cache.GetOrFetchAsync(Url);

        // Smallest allowed size (92) still exceeds the 64px original — never upscale.
        ImageResult variant = (await f.Cache.GetVariantAsync(hash, 92))!;
        Assert.Equal(original.Path, variant.Path);
        Assert.False(f.ImageStore.VariantExists(hash, 92));
    }

    [Fact]
    public async Task Variant_unknown_hash_or_disallowed_size_returns_null()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(200, MakeJpeg(400, 200), "image/jpeg", null, null, null);

        Assert.Null(await f.Cache.GetVariantAsync(new string('0', 64), 185));

        string hash = UpstreamCache.ComputeKey(Url);
        await f.Cache.GetOrFetchAsync(Url);
        Assert.Null(await f.Cache.GetVariantAsync(hash, 13)); // not in the allowed size set
    }

    [Fact]
    public async Task Evicting_the_original_removes_its_variants()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(200, MakeJpeg(400, 200), "image/jpeg", null, null, null);
        string hash = UpstreamCache.ComputeKey(Url);
        await f.Cache.GetOrFetchAsync(Url);
        await f.Cache.GetVariantAsync(hash, 185);

        f.ImageStore.Delete(hash);

        Assert.False(f.ImageStore.VariantExists(hash, 185));
    }

    /// <summary>A real JPEG with the given dimensions (ImageSharp), so resize paths decode real data.</summary>
    private static byte[] MakeJpeg(int width, int height)
    {
        using var image = new Image<Rgba32>(width, height, Color.RoyalBlue);
        using var ms = new MemoryStream();
        image.Save(ms, new JpegEncoder());
        return ms.ToArray();
    }
}
