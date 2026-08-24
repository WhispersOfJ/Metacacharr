namespace Metacache.Core.Cache;

/// <summary>
/// Freshness policy for one class of upstream content (DESIGN.md §7.2 TTL table).
/// </summary>
/// <param name="Ttl">How long a fetched entry is considered fresh.</param>
/// <param name="ServeStaleOnError">Serve an expired entry when upstream fails (stale-if-error).</param>
/// <param name="MaxStaleAge">Hard ceiling on stale-serving age; null = unbounded (offline mode).</param>
public sealed record CachePolicy(
    TimeSpan Ttl,
    bool ServeStaleOnError = true,
    TimeSpan? MaxStaleAge = null)
{
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
