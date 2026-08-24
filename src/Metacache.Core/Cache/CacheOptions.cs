namespace Metacache.Core.Cache;

/// <summary>Configuration for the cache stack (SQLite store + image store).</summary>
public sealed record CacheOptions(
    string DataSource,
    string ImageDirectory,
    long MaxImageBytes = 20L * 1024 * 1024,
    long MaxImageTotalBytes = 10L * 1024 * 1024 * 1024);
