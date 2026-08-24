namespace Metacache.Core.Cache;

/// <summary>
/// Freshness policy for one class of upstream content (DESIGN.md §7.2 TTL table).
/// </summary>
/// <param name="Ttl">How long a fetched entry is considered fresh.</param>
/// <param name="ServeStaleOnError">Serve an expired entry when upstream fails (stale-if-error).</param>
/// <param name="MaxStaleAge">Hard ceiling on stale-serving age; null = unbounded (offline mode).</param>
/// <param name="MaxRetries">How many times a 429 (Too Many Requests) response is retried (0 disables).</param>
/// <param name="RetryBaseSeconds">Exponential-backoff base for 429 retries without a Retry-After header (wait = base × 2^attempt).</param>
/// <param name="MaxRetryDelay">Cap on any single retry wait (Retry-After or backoff); null = 30 s.</param>
public sealed record CachePolicy(
    TimeSpan Ttl,
    bool ServeStaleOnError = true,
    TimeSpan? MaxStaleAge = null,
    int MaxRetries = 2,
    double RetryBaseSeconds = 1.0,
    TimeSpan? MaxRetryDelay = null)
{
    /// <summary>Cap on any single retry wait, so a distant Retry-After can't stall a refresh for minutes.</summary>
    public TimeSpan EffectiveMaxRetryDelay => MaxRetryDelay ?? TimeSpan.FromSeconds(30);

    public static CachePolicy For(TimeSpan ttl, TimeSpan? maxStaleAge = null) =>
        new(ttl, ServeStaleOnError: true, MaxStaleAge: maxStaleAge);
}

/// <summary>Identifies one normalized metadata item in the items store.</summary>
public sealed record ItemDescriptor(
    string Id,
    string Kind,
    string Source,
    string SourceId,
    string Lang);

public sealed record ItemFetchResult(string Json, string? ETag);
