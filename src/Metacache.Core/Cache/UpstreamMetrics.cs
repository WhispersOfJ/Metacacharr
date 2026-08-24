namespace Metacache.Core.Cache;

/// <summary>Per-provider histogram of upstream request durations (seconds).</summary>
public sealed record ProviderDurationHistogram(string Provider, long[] BucketCounts, double Sum, long Count);

/// <summary>Point-in-time copy of the upstream observability state, for rendering.</summary>
public sealed record UpstreamMetricsSnapshot(
    IReadOnlyList<ProviderDurationHistogram> Histograms,
    int? RateLimitRemaining,
    int? RateLimitLimit,
    IReadOnlyDictionary<string, long> RateLimitedCounts);

/// <summary>
/// Process-lifetime upstream observability for /metrics/prometheus: request-duration
/// histograms per provider (the provider label is derived from the request host, e.g.
/// "tmdb" for api.themoviedb.org, "images" for image.tmdb.org) and the TMDB API
/// rate-limit state from the latest response's X-RateLimit-* headers. Only real
/// upstream requests are observed — cache hits never touch this.
/// </summary>
public sealed class UpstreamMetrics
{
    /// <summary>Duration buckets in seconds (the +Inf bucket is implicit in the total).</summary>
    public static readonly double[] DurationBuckets = [0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10];

    private readonly object _gate = new();
    private readonly Dictionary<string, long[]> _bucketCounts = new(StringComparer.Ordinal);
    private readonly Dictionary<string, double> _sums = new(StringComparer.Ordinal);
    private readonly Dictionary<string, long> _counts = new(StringComparer.Ordinal);
    private readonly Dictionary<string, long> _rateLimitedCounts = new(StringComparer.Ordinal);
    private int? _rateLimitRemaining;
    private int? _rateLimitLimit;

    /// <summary>Records one upstream request of <paramref name="seconds"/> for <paramref name="provider"/>.</summary>
    public void Observe(string provider, double seconds)
    {
        lock (_gate)
        {
            if (!_bucketCounts.TryGetValue(provider, out long[]? buckets))
            {
                buckets = new long[DurationBuckets.Length];
                _bucketCounts[provider] = buckets;
            }

            // Cumulative semantics: every bucket whose upper bound is ≥ the observation
            // gets +1 (observations above the last bucket only count in the +Inf total).
            int index = -1;
            for (int i = 0; i < DurationBuckets.Length; i++)
            {
                if (seconds <= DurationBuckets[i])
                {
                    index = i;
                    break;
                }
            }
            // Observations above the last bucket land only in the +Inf total (h.Count).
            if (index >= 0)
            {
                for (int i = index; i < buckets.Length; i++)
                    buckets[i]++;
            }

            _sums.TryGetValue(provider, out double sum);
            _sums[provider] = sum + seconds;
            _counts.TryGetValue(provider, out long count);
            _counts[provider] = count + 1;
        }
    }

    /// <summary>Counts one 429 (Too Many Requests) response for <paramref name="provider"/>.</summary>
    public void ObserveRateLimited(string provider)
    {
        lock (_gate)
        {
            _rateLimitedCounts.TryGetValue(provider, out long count);
            _rateLimitedCounts[provider] = count + 1;
        }
    }

    /// <summary>Publishes the rate-limit state from a response's X-RateLimit-* headers (nulls leave the value unchanged).</summary>
    public void ObserveRateLimit(int? remaining, int? limit)
    {
        lock (_gate)
        {
            if (remaining is not null)
                _rateLimitRemaining = remaining;
            if (limit is not null)
                _rateLimitLimit = limit;
        }
    }

    public UpstreamMetricsSnapshot Snapshot()
    {
        lock (_gate)
        {
            var histograms = _bucketCounts
                .OrderBy(p => p.Key, StringComparer.Ordinal)
                .Select(p => new ProviderDurationHistogram(
                    p.Key, (long[])p.Value.Clone(), _sums[p.Key], _counts[p.Key]))
                .ToList();
            var rateLimited = _rateLimitedCounts
                .OrderBy(p => p.Key, StringComparer.Ordinal)
                .ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
            return new UpstreamMetricsSnapshot(histograms, _rateLimitRemaining, _rateLimitLimit, rateLimited);
        }
    }
}
