using Microsoft.Extensions.Logging;

namespace Metacache.Core.Cache;

public enum ImageSource
{
    /// <summary>Served from the local file store.</summary>
    Cache,

    /// <summary>Fetched from upstream and stored on this call.</summary>
    Upstream
}

public sealed record ImageResult(string Hash, string Path, string ContentType, ImageSource Source);

/// <summary>
/// The image cache (DESIGN.md §7.3): content-addressed files keyed by the sha256 of the
/// original URL, recorded in the `urls` table, single-flighted so a herd of identical
/// artwork requests triggers one upstream fetch. Images are treated as immutable — no
/// TTL/expiry; the store is bounded by the per-file cap and a total-bytes cap that
/// evicts oldest-first. /img/{hash} is self-healing: a miss for a known hash refetches.
/// </summary>
public sealed class ImageCache
{
    private readonly CacheStore _cache;
    private readonly ImageStore _store;
    private readonly IUpstreamHttp _upstream;
    private readonly SingleFlight _flight;
    private readonly IClock _clock;
    private readonly UpstreamMetrics _metrics;
    private readonly long _maxTotalBytes;
    private readonly ILogger<ImageCache> _logger;

    public ImageCache(
        CacheStore cache,
        ImageStore store,
        IUpstreamHttp upstream,
        SingleFlight flight,
        IClock clock,
        UpstreamMetrics metrics,
        ILogger<ImageCache> logger,
        long maxTotalBytes)
    {
        _cache = cache;
        _store = store;
        _upstream = upstream;
        _flight = flight;
        _clock = clock;
        _metrics = metrics;
        _maxTotalBytes = maxTotalBytes;
        _logger = logger;
    }

    /// <summary>Rewrites an upstream artwork URL to the local /img/{hash} path the mapper returns to Plex.</summary>
    public static string RewriteToLocalPath(string upstreamUrl) =>
        $"/img/{UpstreamCache.ComputeKey(upstreamUrl)}";

    /// <summary>
    /// Registers an upstream image URL in the `urls` table WITHOUT fetching, so that
    /// /img/{hash} can resolve it on the first request (fetch + store). The mapper
    /// rewrites artwork to /img/{hash}; this makes those hashes known before any
    /// fetch happens — otherwise the first Plex image request for a fresh match 404s.
    /// Idempotent: an existing row (e.g. one with a real file path) is left untouched.
    /// </summary>
    public void RegisterUrl(string url)
    {
        ArgumentException.ThrowIfNullOrEmpty(url);
        string hash = UpstreamCache.ComputeKey(url);
        if (_cache.GetUrl(hash) is not null)
            return;
        _cache.PutUrl(new CachedUrl(hash, url, Path: "", Size: 0, FetchedAt: _clock.UtcNow));
    }

    /// <summary>Returns the image, fetching and storing it on miss.</summary>
    public async Task<ImageResult> GetOrFetchAsync(string url, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(url);
        cancellationToken.ThrowIfCancellationRequested();

        string hash = UpstreamCache.ComputeKey(url);
        if (_store.Exists(hash))
            return Result(hash, url, ImageSource.Cache);

        Task<ImageResult> task = _flight.RunAsync(hash, () => FetchCoreAsync(hash, url));
        return await task.ConfigureAwait(false);
    }

    /// <summary>
    /// Resolves an /img/{hash} request: a stored URL for that hash is served (fetching on
    /// miss); unknown hashes return null. Hash validity is assumed checked by the caller
    /// (the endpoint validates before calling).
    /// </summary>
    public async Task<ImageResult?> GetByHashAsync(string hash, CancellationToken cancellationToken = default)
    {
        CachedUrl? row = _cache.GetUrl(hash);
        return row is null ? null : await GetOrFetchAsync(row.Url, cancellationToken).ConfigureAwait(false);
    }

    private async Task<ImageResult> FetchCoreAsync(string hash, string url)
    {
        // Another caller may have stored the file while we waited for the flight.
        if (_store.Exists(hash))
            return Result(hash, url, ImageSource.Cache);

        UpstreamResponse upstream;
        var sw = System.Diagnostics.Stopwatch.StartNew();
        try
        {
            upstream = await _upstream
                .SendAsync(new UpstreamRequest(new Uri(url)), CancellationToken.None)
                .ConfigureAwait(false);
        }
        finally
        {
            sw.Stop();
            _metrics.Observe("images", sw.Elapsed.TotalSeconds);
        }

        if (upstream.StatusCode is < 200 or >= 300)
            throw new UpstreamException(upstream.StatusCode, upstream.RetryAfter,
                $"Image fetch returned {upstream.StatusCode} for {url}");

        string path = _store.Store(hash, upstream.Body); // enforces the per-file cap
        _cache.PutUrl(new CachedUrl(hash, url, path, upstream.Body.Length, _clock.UtcNow));
        EnforceTotalCap();
        _logger.LogDebug("Cached image {Hash} ({Size} bytes) from {Url}", hash, upstream.Body.Length, url);
        return new ImageResult(hash, path, ImageContentTypes.FromUrl(url), ImageSource.Upstream);
    }

    private ImageResult Result(string hash, string url, ImageSource source) =>
        new(hash, _store.GetFilePath(hash), ImageContentTypes.FromUrl(url), source);

    private void EnforceTotalCap()
    {
        if (_cache.SumUrlBytes() <= _maxTotalBytes)
            return;

        _logger.LogWarning("Image cache exceeds the {Cap}-byte cap; evicting oldest entries", _maxTotalBytes);
        foreach (CachedUrl oldest in _cache.GetOldestUrls(1024))
        {
            if (_cache.SumUrlBytes() <= _maxTotalBytes)
                break;
            _cache.DeleteUrl(oldest.Hash);
            _store.Delete(oldest.Hash);
        }
    }
}
