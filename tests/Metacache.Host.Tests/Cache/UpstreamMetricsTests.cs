using Metacache.Core.Cache;

namespace Metacache.Host.Tests.Cache;

public class UpstreamMetricsTests
{
    [Fact]
    public void Observations_land_in_cumulative_buckets_per_provider()
    {
        var metrics = new UpstreamMetrics();
        metrics.Observe("tmdb", 0.04);   // le=0.05
        metrics.Observe("tmdb", 0.2);    // le=0.25
        metrics.Observe("tmdb", 3.0);    // le=5
        metrics.Observe("images", 0.1);  // le=0.1, separate provider

        UpstreamMetricsSnapshot snapshot = metrics.Snapshot();

        Assert.Equal(2, snapshot.Histograms.Count);
        ProviderDurationHistogram tmdb = Assert.Single(snapshot.Histograms, h => h.Provider == "tmdb");
        ProviderDurationHistogram images = Assert.Single(snapshot.Histograms, h => h.Provider == "images");

        // Cumulative buckets: 0.04s ≤ every bound, 0.2s ≤ 0.25s+, 3.0s ≤ 5s+.
        Assert.Equal(3, tmdb.Count);
        Assert.Equal(new long[] { 1, 1, 2, 2, 2, 2, 3, 3 }, tmdb.BucketCounts);
        Assert.Equal(3.24, tmdb.Sum, precision: 10);
        Assert.Equal(3, tmdb.BucketCounts[^1]);  // ≤ last bucket == total

        // 0.1s ≤ 0.1s and every larger bound.
        Assert.Equal(1, images.Count);
        Assert.Equal(new long[] { 0, 1, 1, 1, 1, 1, 1, 1 }, images.BucketCounts);
    }

    [Fact]
    public void Rate_limit_state_starts_unknown_and_updates()
    {
        var metrics = new UpstreamMetrics();

        Assert.Null(metrics.Snapshot().RateLimitRemaining);
        Assert.Null(metrics.Snapshot().RateLimitLimit);

        metrics.ObserveRateLimit(39, 40);
        metrics.ObserveRateLimit(38, null); // partial updates leave other fields

        UpstreamMetricsSnapshot snapshot = metrics.Snapshot();
        Assert.Equal(38, snapshot.RateLimitRemaining);
        Assert.Equal(40, snapshot.RateLimitLimit);
    }

    [Fact]
    public void Observation_above_the_last_bucket_counts_only_in_the_total()
    {
        var metrics = new UpstreamMetrics();

        // Regression: seconds > 10 (the last bucket) used to walk the array from
        // index -1 and throw IndexOutOfRangeException inside the fetch finally.
        metrics.Observe("tmdb", 15.0);

        ProviderDurationHistogram tmdb = Assert.Single(metrics.Snapshot().Histograms);
        Assert.Equal(1, tmdb.Count);          // +Inf total includes it
        Assert.Equal(15.0, tmdb.Sum, precision: 10);
        Assert.All(tmdb.BucketCounts, b => Assert.Equal(0, b)); // no finite bucket holds it
    }

    [Fact]
    public void Rate_limited_counts_accumulate_per_provider()
    {
        var metrics = new UpstreamMetrics();

        metrics.ObserveRateLimited("tmdb");
        metrics.ObserveRateLimited("tmdb");
        metrics.ObserveRateLimited("images");

        UpstreamMetricsSnapshot snapshot = metrics.Snapshot();
        Assert.Equal(2, snapshot.RateLimitedCounts["tmdb"]);
        Assert.Equal(1, snapshot.RateLimitedCounts["images"]);
    }

    [Fact]
    public void Snapshot_isolates_the_internal_bucket_state()
    {
        var metrics = new UpstreamMetrics();
        metrics.Observe("tmdb", 0.5);

        UpstreamMetricsSnapshot first = metrics.Snapshot();
        first.Histograms[0].BucketCounts[0] = 999; // mutate the copy

        UpstreamMetricsSnapshot second = metrics.Snapshot();
        Assert.Equal(0, second.Histograms[0].BucketCounts[0]);
        Assert.Equal(1, second.Histograms[0].Count);
    }
}
