using System.Text;
using Metacache.Core.Cache;
using Microsoft.Extensions.Logging.Abstractions;

namespace Metacache.Host.Tests.Cache;

public class UpstreamCacheTests
{
    private const string Url = "https://api.themoviedb.org/3/movie/105?language=en-US";
    private const string EtagV1 = "w/\"v1\"";

    private sealed class Fixture : IDisposable
    {
        public FakeClock Clock { get; } = new(DateTimeOffset.Parse("2026-08-24T00:00:00+00:00"));
        public FakeUpstream Upstream { get; } = new();
        public UpstreamMetrics Metrics { get; } = new();
        public CacheStore Store { get; }
        public UpstreamCache Cache { get; }

        public Fixture()
        {
            Store = new CacheStore(":memory:", Clock);
            Cache = new UpstreamCache(Store, Upstream, new SingleFlight(), Clock, Metrics, NullLogger<UpstreamCache>.Instance);
        }

        public void Dispose() => Store.Dispose();

        public void SeedFresh(string body = "fresh-body", string etag = EtagV1)
        {
            var now = Clock.UtcNow;
            Store.PutUpstream(new CachedUpstreamRow(
                UpstreamCache.ComputeKey(Url), Url, 200, "application/json", TestBytes.Of(body),
                now.AddMinutes(-1), now.AddHours(1), etag, null, 0));
        }

        public void SeedStale(string body = "old-body", string etag = EtagV1)
        {
            var now = Clock.UtcNow;
            Store.PutUpstream(new CachedUpstreamRow(
                UpstreamCache.ComputeKey(Url), Url, 200, "application/json", TestBytes.Of(body),
                now.AddHours(-2), now.AddHours(-1), etag, null, 0));
        }
    }

    private static UpstreamResponse Ok(string body, string? etag = EtagV1) =>
        new(200, TestBytes.Of(body), "application/json", etag, null, null);

    private static UpstreamResponse NotModified() =>
        new(304, [], null, null, null, null);

    private static UpstreamResponse Error(int status, DateTimeOffset? retryAfter = null) =>
        new(status, TestBytes.Of("error"), "text/plain", null, null, retryAfter);

    private static CachePolicy Hour() => CachePolicy.For(TimeSpan.FromHours(1));

    [Fact]
    public async Task Miss_fetches_once_then_serves_from_cache()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Ok("hello");

        var first = await f.Cache.GetOrFetchAsync(Url, Hour());
        var second = await f.Cache.GetOrFetchAsync(Url, Hour());

        Assert.Equal(CacheSource.Upstream, first.Source);
        Assert.Equal(CacheSource.Cache, second.Source);
        Assert.Equal("hello", TestBytes.Read(second.Body));
        Assert.Single(f.Upstream.Requests);
    }

    [Fact]
    public async Task Fresh_entry_is_served_without_contacting_upstream()
    {
        using var f = new Fixture();
        f.SeedFresh();
        f.Upstream.Handler = _ => throw new InvalidOperationException("upstream must not be called");

        var result = await f.Cache.GetOrFetchAsync(Url, Hour());

        Assert.Equal(CacheSource.Cache, result.Source);
        Assert.Equal("fresh-body", TestBytes.Read(result.Body));
        Assert.Empty(f.Upstream.Requests);
    }

    [Fact]
    public async Task Stale_entry_revalidates_with_conditional_request_and_304_refreshes_ttl()
    {
        using var f = new Fixture();
        f.SeedStale(body: "old-body", etag: EtagV1);
        f.Upstream.Handler = request =>
        {
            Assert.Equal(EtagV1, request.IfNoneMatch);
            return NotModified();
        };

        var result = await f.Cache.GetOrFetchAsync(Url, Hour());

        Assert.Equal(CacheSource.Revalidated, result.Source);
        Assert.Equal("old-body", TestBytes.Read(result.Body)); // body unchanged
        CachedUpstreamRow? stored = f.Store.GetUpstream(UpstreamCache.ComputeKey(Url));
        Assert.True(stored!.ExpiresAt > f.Clock.UtcNow, "TTL should be refreshed after 304");
        Assert.Single(f.Upstream.Requests);
    }

    [Fact]
    public async Task Stale_entry_is_updated_when_upstream_returns_200()
    {
        using var f = new Fixture();
        f.SeedStale(body: "old-body");
        f.Upstream.Handler = _ => Ok("new-body", etag: "w/\"v2\"");

        var result = await f.Cache.GetOrFetchAsync(Url, Hour());

        Assert.Equal(CacheSource.Upstream, result.Source);
        Assert.Equal("new-body", TestBytes.Read(result.Body));
        CachedUpstreamRow? stored = f.Store.GetUpstream(UpstreamCache.ComputeKey(Url));
        Assert.Equal("new-body", TestBytes.Read(stored!.Body));
        Assert.Equal("w/\"v2\"", stored.ETag);
    }

    [Fact]
    public async Task Stale_is_served_when_upstream_transport_fails()
    {
        using var f = new Fixture();
        f.SeedStale(body: "old-body");
        f.Upstream.Handler = _ => throw new HttpRequestException("connection refused");

        var result = await f.Cache.GetOrFetchAsync(Url, Hour());

        Assert.Equal(CacheSource.Stale, result.Source);
        Assert.Equal("old-body", TestBytes.Read(result.Body));
    }

    [Fact]
    public async Task Stale_is_served_when_upstream_returns_5xx()
    {
        using var f = new Fixture();
        f.SeedStale(body: "old-body");
        f.Upstream.Handler = _ => Error(503);

        var result = await f.Cache.GetOrFetchAsync(Url, Hour());

        Assert.Equal(CacheSource.Stale, result.Source);
        Assert.Equal("old-body", TestBytes.Read(result.Body));
    }

    [Fact]
    public async Task Stale_is_not_served_beyond_max_stale_age()
    {
        using var f = new Fixture();
        f.SeedStale(body: "old-body");
        f.Upstream.Handler = _ => Error(503);
        var policy = CachePolicy.For(TimeSpan.FromHours(1), maxStaleAge: TimeSpan.FromHours(1));

        var ex = await Assert.ThrowsAsync<UpstreamException>(() => f.Cache.GetOrFetchAsync(Url, policy));

        Assert.Equal(503, ex.StatusCode);
    }

    [Fact]
    public async Task Miss_with_5xx_throws_and_is_not_poisoned_for_retry()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Error(500);

        var ex = await Assert.ThrowsAsync<UpstreamException>(() => f.Cache.GetOrFetchAsync(Url, Hour()));
        Assert.Equal(500, ex.StatusCode);

        // A later successful fetch still works and caches.
        f.Upstream.Handler = _ => Ok("recovered");
        var result = await f.Cache.GetOrFetchAsync(Url, Hour());
        Assert.Equal(CacheSource.Upstream, result.Source);
        Assert.Equal("recovered", TestBytes.Read(result.Body));
    }

    [Fact]
    public async Task Miss_with_transport_failure_throws_status_zero()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => throw new HttpRequestException("dns failed");

        var ex = await Assert.ThrowsAsync<UpstreamException>(() => f.Cache.GetOrFetchAsync(Url, Hour()));

        Assert.Equal(0, ex.StatusCode);
    }

    [Fact]
    public async Task Concurrent_miss_causes_single_upstream_call()
    {
        using var f = new Fixture();
        int calls = 0;
        f.Upstream.Handler = _ =>
        {
            Interlocked.Increment(ref calls);
            Thread.Sleep(30);
            return Ok("hello");
        };

        Task<CachedResponse>[] tasks = Enumerable.Range(0, 8)
            .Select(_ => f.Cache.GetOrFetchAsync(Url, Hour()))
            .ToArray();
        CachedResponse[] results = await Task.WhenAll(tasks);

        Assert.All(results, r => Assert.Equal("hello", TestBytes.Read(r.Body)));
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task Caller_cancellation_does_not_abort_shared_fetch()
    {
        using var f = new Fixture();
        using var cts = new CancellationTokenSource();
        f.Upstream.Handler = _ => Ok("hello");

        Task<CachedResponse> canceledCall = f.Cache.GetOrFetchAsync(Url, Hour(), cts.Token);
        cts.Cancel();

        // The shared fetch still completes and populates the cache for others.
        var result = await f.Cache.GetOrFetchAsync(Url, Hour());

        Assert.Equal(CacheSource.Cache, result.Source);
        Assert.Single(f.Upstream.Requests);
        Assert.True(canceledCall.IsCompleted);
    }

    [Fact]
    public async Task Cache_hits_are_counted()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Ok("hello");

        await f.Cache.GetOrFetchAsync(Url, Hour());
        await f.Cache.GetOrFetchAsync(Url, Hour());
        await f.Cache.GetOrFetchAsync(Url, Hour());

        CachedUpstreamRow? stored = f.Store.GetUpstream(UpstreamCache.ComputeKey(Url));
        Assert.Equal(2, stored!.Hits);
    }

    [Fact]
    public async Task Upstream_requests_are_recorded_in_the_duration_histogram()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Ok("hello");

        await f.Cache.GetOrFetchAsync(Url, Hour()); // miss → one upstream request
        await f.Cache.GetOrFetchAsync(Url, Hour()); // hit → no upstream request

        UpstreamMetricsSnapshot snapshot = f.Metrics.Snapshot();
        ProviderDurationHistogram tmdb = Assert.Single(snapshot.Histograms);
        Assert.Equal("tmdb", tmdb.Provider); // derived from api.themoviedb.org
        Assert.Equal(1, tmdb.Count);          // only the miss is observed
        Assert.True(tmdb.Sum >= 0);
        Assert.Equal(tmdb.Count, tmdb.BucketCounts[^1]);
    }

    [Fact]
    public async Task Rate_limit_headers_are_recorded_from_upstream_responses()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => new UpstreamResponse(
            200, TestBytes.Of("hello"), "application/json", null, null, null,
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                ["X-RateLimit-Remaining"] = "39",
                ["X-RateLimit-Limit"] = "40"
            });

        await f.Cache.GetOrFetchAsync(Url, Hour());

        UpstreamMetricsSnapshot snapshot = f.Metrics.Snapshot();
        Assert.Equal(39, snapshot.RateLimitRemaining);
        Assert.Equal(40, snapshot.RateLimitLimit);
    }

    [Fact]
    public async Task Rate_limited_responses_are_counted_per_provider()
    {
        using var f = new Fixture();
        f.SeedStale(body: "old-body");
        f.Upstream.Handler = _ => Error(429, retryAfter: DateTimeOffset.UtcNow.AddSeconds(10));

        // 429 with a stale entry → served stale; the throttle is still counted.
        var result = await f.Cache.GetOrFetchAsync(Url, Hour());
        Assert.Equal(CacheSource.Stale, result.Source);

        Assert.Equal(1, f.Metrics.Snapshot().RateLimitedCounts["tmdb"]);
    }

    [Fact]
    public async Task Process_counters_track_hits_and_misses_for_metrics()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Ok("hello");

        Assert.Equal(0, f.Cache.GetCounters().Requests);

        await f.Cache.GetOrFetchAsync(Url, Hour()); // miss
        await f.Cache.GetOrFetchAsync(Url, Hour()); // hit
        await f.Cache.GetOrFetchAsync(Url, Hour()); // hit

        CacheCounters counters = f.Cache.GetCounters();
        Assert.Equal(3, counters.Requests);
        Assert.Equal(2, counters.Hits);
        Assert.Equal(1, counters.Misses);
        Assert.Equal(2.0 / 3.0, counters.HitRate, precision: 3);
    }

    [Fact]
    public async Task Not_found_is_passed_through_and_not_cached()
    {
        using var f = new Fixture();
        f.Upstream.Handler = _ => Error(404);

        var result = await f.Cache.GetOrFetchAsync(Url, Hour());

        Assert.Equal(404, result.StatusCode);
        Assert.Null(f.Store.GetUpstream(UpstreamCache.ComputeKey(Url)));

        await f.Cache.GetOrFetchAsync(Url, Hour());
        Assert.Equal(2, f.Upstream.Requests.Count); // every 404 hits upstream again
    }

    [Fact]
    public async Task Extra_headers_are_forwarded_to_upstream()
    {
        using var f = new Fixture();
        var headers = new Dictionary<string, string> { ["Authorization"] = "Bearer secret-key" };
        f.Upstream.Handler = request =>
        {
            Assert.Equal("Bearer secret-key", request.Headers!["Authorization"]);
            return Ok("hello");
        };

        await f.Cache.GetOrFetchAsync(Url, Hour(), headers: headers);

        // Cached follow-up calls do not need headers, but the fetch path carries them.
        await f.Cache.GetOrFetchAsync(Url, Hour(), headers: headers);
        Assert.Single(f.Upstream.Requests);
    }

    [Fact]
    public void ComputeKey_is_a_deterministic_sha256_hex()
    {
        Assert.Equal(64, UpstreamCache.ComputeKey(Url).Length);
        Assert.Equal(UpstreamCache.ComputeKey(Url), UpstreamCache.ComputeKey(Url));
        Assert.NotEqual(UpstreamCache.ComputeKey(Url), UpstreamCache.ComputeKey(Url + "&page=2"));
    }
}
