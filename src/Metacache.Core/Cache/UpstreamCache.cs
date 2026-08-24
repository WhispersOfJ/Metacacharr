using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Logging;

namespace Metacache.Core.Cache;

/// <summary>
/// The raw-HTTP cache gateway (DESIGN.md §7). Serves fresh entries from the store,
/// revalidates stale entries with conditional requests (If-None-Match /
/// If-Modified-Since), refreshes TTL on 304, and falls back to serving stale content
/// when upstream fails (stale-if-error) — so a library keeps working with the WAN down.
///
/// All fetch work for a URL is single-flighted so concurrent callers trigger one
/// upstream request. Callers must normalize URLs (strip API keys, sort query params)
/// before calling; the cache key is the sha256 of the URL string as given.
/// </summary>
public sealed class UpstreamCache
{
    private readonly CacheStore _store;
    private readonly IUpstreamHttp _upstream;
    private readonly SingleFlight _flight;
    private readonly IClock _clock;
    private readonly ILogger<UpstreamCache> _logger;

    public UpstreamCache(
        CacheStore store,
        IUpstreamHttp upstream,
        SingleFlight flight,
        IClock clock,
        ILogger<UpstreamCache> logger)
    {
        _store = store;
        _upstream = upstream;
        _flight = flight;
        _clock = clock;
        _logger = logger;
    }

    public static string ComputeKey(string url)
    {
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(url));
        return Convert.ToHexStringLower(hash);
    }

    public async Task<CachedResponse> GetOrFetchAsync(
        string url,
        CachePolicy policy,
        CancellationToken cancellationToken = default,
        IReadOnlyDictionary<string, string>? headers = null,
        string? cacheKey = null)
    {
        ArgumentException.ThrowIfNullOrEmpty(url);
        cancellationToken.ThrowIfCancellationRequested();

        // cacheKey override: callers that must embed secrets in the request URL (e.g.
        // TMDB's legacy api_key query param) compute the key from the secret-free URL
        // so keys and the DB never contain credentials.
        string key = cacheKey ?? ComputeKey(url);
        Task<CachedResponse> task = _flight.RunAsync(key, () => FetchCoreAsync(key, url, policy, headers));
        return await task.ConfigureAwait(false);
    }

    private async Task<CachedResponse> FetchCoreAsync(string key, string url, CachePolicy policy, IReadOnlyDictionary<string, string>? headers)
    {
        CachedUpstreamRow? cached = _store.GetUpstream(key);
        DateTimeOffset now = _clock.UtcNow;

        if (cached is not null && cached.ExpiresAt > now)
        {
            _store.BumpHits(key);
            return cached.ToResponse(CacheSource.Cache);
        }

        if (cached is not null)
        {
            // Stale → revalidate with a conditional request.
            try
            {
                var request = new UpstreamRequest(new Uri(url), cached.ETag, cached.LastModified, headers);
                var upstream = await _upstream.SendAsync(request, CancellationToken.None).ConfigureAwait(false);
                return HandleUpstreamResponse(upstream, key, url, cached, policy, now);
            }
            catch (HttpRequestException ex)
            {
                _logger.LogWarning(ex, "Upstream transport failure revalidating {Url}; serving stale", url);
                return ServeStaleOrThrow(cached, policy, now,
                    new UpstreamException(0, null, $"Transport failure for {url}: {ex.Message}"));
            }
        }

        // Cold miss.
        try
        {
            var upstream = await _upstream.SendAsync(new UpstreamRequest(new Uri(url), Headers: headers), CancellationToken.None).ConfigureAwait(false);
            return HandleUpstreamResponse(upstream, key, url, cached: null, policy, now);
        }
        catch (HttpRequestException ex)
        {
            throw new UpstreamException(0, null, $"Transport failure for {url}: {ex.Message}");
        }
    }

    private CachedResponse HandleUpstreamResponse(
        UpstreamResponse upstream, string key, string url, CachedUpstreamRow? cached, CachePolicy policy, DateTimeOffset now)
    {
        // 304: content unchanged — refresh the TTL on the existing entry.
        if (upstream.StatusCode == 304 && cached is not null)
        {
            var refreshed = cached with { FetchedAt = now, ExpiresAt = now + policy.Ttl };
            _store.PutUpstream(refreshed);
            _store.BumpHits(key);
            _logger.LogDebug("Revalidated {Url} (304); TTL refreshed", url);
            return refreshed.ToResponse(CacheSource.Revalidated);
        }

        // 2xx: store the fresh body (with validators for next revalidation).
        if (upstream.StatusCode is >= 200 and < 300)
        {
            var fresh = new CachedUpstreamRow(
                key, url, upstream.StatusCode, upstream.ContentType, upstream.Body,
                now, now + policy.Ttl, upstream.ETag, upstream.LastModified, Hits: 0);
            _store.PutUpstream(fresh);
            return fresh.ToResponse(CacheSource.Upstream);
        }

        // 404 is not cached (a negative hit) — pass it through so callers can map it.
        if (upstream.StatusCode == 404)
        {
            return new CachedResponse(404, [], null, CacheSource.Upstream);
        }

        // 429 / 5xx / other: stale fallback or error.
        var error = new UpstreamException(
            upstream.StatusCode, upstream.RetryAfter,
            $"Upstream returned {upstream.StatusCode} for {url}");
        if (cached is not null)
            return ServeStaleOrThrow(cached, policy, now, error);
        throw error;
    }

    private CachedResponse ServeStaleOrThrow(CachedUpstreamRow cached, CachePolicy policy, DateTimeOffset now, UpstreamException error)
    {
        if (!policy.ServeStaleOnError)
            throw error;
        if (policy.MaxStaleAge is { } max && now - cached.FetchedAt > max)
            throw error;

        _logger.LogWarning(error, "Serving stale cache entry for {Url} (fetched {FetchedAt})", cached.Url, cached.FetchedAt);
        _store.BumpHits(cached.Key);
        return cached.ToResponse(CacheSource.Stale);
    }
}
