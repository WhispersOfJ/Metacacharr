using Metacache.Core.Cache;

namespace Metacache.Host.Tests.Cache;

public class MetadataCacheTests
{
    private static readonly ItemDescriptor Descriptor = new("tmdb-movie-105", "movie", "tmdb", "105", "en-US");

    private sealed class Fixture : IDisposable
    {
        public FakeClock Clock { get; } = new(DateTimeOffset.Parse("2026-08-24T00:00:00+00:00"));
        public CacheStore Store { get; }
        public MetadataCache Cache { get; }

        public Fixture()
        {
            Store = new CacheStore(":memory:", Clock);
            Cache = new MetadataCache(Store, new SingleFlight(), Clock);
        }

        public void Dispose() => Store.Dispose();

        public void SeedFresh(string json = "{\"title\":\"Back to the Future\"}")
        {
            var now = Clock.UtcNow;
            Store.PutItem(new CachedItem(Descriptor.Id, Descriptor.Kind, Descriptor.Source, Descriptor.SourceId,
                Descriptor.Lang, json, now.AddMinutes(-1), now.AddHours(1), "w/\"e1\""));
        }

        public void SeedStale(string json = "{\"title\":\"Old\"}")
        {
            var now = Clock.UtcNow;
            Store.PutItem(new CachedItem(Descriptor.Id, Descriptor.Kind, Descriptor.Source, Descriptor.SourceId,
                Descriptor.Lang, json, now.AddHours(-2), now.AddHours(-1), "w/\"e1\""));
        }
    }

    private static CachePolicy Hour() => CachePolicy.For(TimeSpan.FromHours(1));

    private static Task<ItemFetchResult> Json(string json, string? etag = null) =>
        Task.FromResult(new ItemFetchResult(json, etag));

    [Fact]
    public async Task Fresh_item_is_served_without_calling_fetcher()
    {
        using var f = new Fixture();
        f.SeedFresh();

        CachedItem item = await f.Cache.GetOrFetchAsync(Descriptor,
            _ => throw new InvalidOperationException("fetcher must not run"), Hour());

        Assert.Equal("{\"title\":\"Back to the Future\"}", item.Json);
    }

    [Fact]
    public async Task Stale_item_is_refetched_and_stored()
    {
        using var f = new Fixture();
        f.SeedStale();
        int calls = 0;

        CachedItem item = await f.Cache.GetOrFetchAsync(Descriptor,
            _ => { calls++; return Json("{\"title\":\"New\"}", "w/\"e2\""); }, Hour());

        Assert.Equal("{\"title\":\"New\"}", item.Json);
        Assert.Equal(1, calls);
        CachedItem? stored = f.Store.GetItem(Descriptor.Id, Descriptor.Lang);
        Assert.Equal("{\"title\":\"New\"}", stored!.Json);
        Assert.True(stored.ExpiresAt > f.Clock.UtcNow);
    }

    [Fact]
    public async Task Fetcher_failure_returns_stale_item()
    {
        using var f = new Fixture();
        f.SeedStale(json: "{\"title\":\"Last Good\"}");

        CachedItem item = await f.Cache.GetOrFetchAsync(Descriptor,
            _ => throw new HttpRequestException("offline"), Hour());

        Assert.Equal("{\"title\":\"Last Good\"}", item.Json);
    }

    [Fact]
    public async Task Miss_with_fetcher_failure_throws()
    {
        using var f = new Fixture();

        await Assert.ThrowsAsync<HttpRequestException>(() =>
            f.Cache.GetOrFetchAsync(Descriptor, _ => throw new HttpRequestException("offline"), Hour()));
    }

    [Fact]
    public async Task Concurrent_requests_run_fetcher_once()
    {
        using var f = new Fixture();
        int calls = 0;

        Task<CachedItem>[] tasks = Enumerable.Range(0, 8)
            .Select(_ => f.Cache.GetOrFetchAsync(Descriptor,
                async _ => { Interlocked.Increment(ref calls); await Task.Delay(20); return new ItemFetchResult("{}", null); },
                Hour()))
            .ToArray();
        CachedItem[] results = await Task.WhenAll(tasks);

        Assert.Equal(8, results.Length);
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task Language_variants_are_fetched_and_cached_separately()
    {
        using var f = new Fixture();
        var german = Descriptor with { Lang = "de-DE" };

        await f.Cache.GetOrFetchAsync(Descriptor, _ => Json("{\"title\":\"English\"}"), Hour());
        await f.Cache.GetOrFetchAsync(german, _ => Json("{\"title\":\"Deutsch\"}"), Hour());

        Assert.Equal("{\"title\":\"English\"}", f.Store.GetItem(Descriptor.Id, "en-US")!.Json);
        Assert.Equal("{\"title\":\"Deutsch\"}", f.Store.GetItem(Descriptor.Id, "de-DE")!.Json);
    }
}
