namespace Metacache.Core.Cache;

/// <summary>Where a served response came from (diagnostics + stats).</summary>
public enum CacheSource
{
    /// <summary>Fetched from upstream and stored (cold miss or TTL refresh).</summary>
    Upstream,

    /// <summary>Served from a fresh cache entry without contacting upstream.</summary>
    Cache,

    /// <summary>Cache entry was stale; a conditional request returned 304 and refreshed it.</summary>
    Revalidated,

    /// <summary>Cache entry was stale and upstream failed; served anyway (stale-if-error).</summary>
    Stale
}

/// <summary>Result of a cache lookup/fetch for one upstream URL.</summary>
public sealed record CachedResponse(
    int StatusCode,
    byte[] Body,
    string? ContentType,
    CacheSource Source);

/// <summary>Raw HTTP cache row (DESIGN.md §7.4 `upstream_cache`). Key = sha256 hex of the URL.</summary>
public sealed record CachedUpstreamRow(
    string Key,
    string Url,
    int Status,
    string? ContentType,
    byte[] Body,
    DateTimeOffset FetchedAt,
    DateTimeOffset ExpiresAt,
    string? ETag,
    DateTimeOffset? LastModified,
    long Hits)
{
    public CachedResponse ToResponse(CacheSource source) =>
        new(Status, Body, ContentType, source);
}

/// <summary>Normalized metadata store row (DESIGN.md §7.4 `items`). Keyed by (id, lang).</summary>
public sealed record CachedItem(
    string Id,
    string Kind,
    string Source,
    string SourceId,
    string Lang,
    string Json,
    DateTimeOffset FetchedAt,
    DateTimeOffset ExpiresAt,
    string? ETag);

/// <summary>Image/asset row (DESIGN.md §7.4 `urls`). Hash = sha256 hex of the original URL.</summary>
public sealed record CachedUrl(
    string Hash,
    string Url,
    string Path,
    long Size,
    DateTimeOffset FetchedAt);

public sealed record CacheStats(int UpstreamEntries, long UpstreamBytes, int ItemEntries, int UrlEntries);
