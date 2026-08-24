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
    private readonly UpstreamMetrics _metrics;
    private readonly ILogger<UpstreamCache> _logger;
    private long _requests;
    private long _hits;

    public UpstreamCache(
        CacheStore store,
        IUpstreamHttp upstream,
        SingleFlight flight,
        IClock clock,
        UpstreamMetrics metrics,
        ILogger<UpstreamCache> logger)
    {
        _store = store;
        _upstream = upstream;
        _flight = flight;
        _clock = clock;
        _metrics = metrics;
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
        Interlocked.Increment(ref _requests);
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
            Interlocked.Increment(ref _hits);
            return cached.ToResponse(CacheSource.Cache);
        }

        try
        {
            UpstreamResponse upstream = await SendWithRetryAsync(url, cached, policy, headers).ConfigureAwait(false);
            return HandleUpstreamResponse(upstream, key, url, cached, policy, now);
        }
        catch (HttpRequestException ex)
        {
            if (cached is not null)
            {
                _logger.LogWarning(ex, "Upstream transport failure revalidating {Url}; serving stale", url);
                return ServeStaleOrThrow(cached, policy, now,
                    new UpstreamException(0, null, $"Transport failure for {url}: {ex.Message}"));
            }
            throw new UpstreamException(0, null, $"Transport failure for {url}: {ex.Message}");
        }
    }

    /// <summary>
    /// Sends the request (conditional when a stale entry exists), retrying 429 (Too Many
    /// Requests) up to <see cref="CachePolicy.MaxRetries"/> times so a rate-limited
    /// refresh waits out the window instead of failing or serving stale. The wait honors
    /// Retry-After when present, otherwise exponential backoff (base × 2^attempt); both
    /// are capped by <see cref="CachePolicy.EffectiveMaxRetryDelay"/>. Every 429 response
    /// is counted for the /metrics/prometheus rate-limited counter.
    /// </summary>
    private async Task<UpstreamResponse> SendWithRetryAsync(
        string url, CachedUpstreamRow? cached, CachePolicy policy, IReadOnlyDictionary<string, string>? headers)
    {
        var request = cached is not null
            ? new UpstreamRequest(new Uri(url), cached.ETag, cached.LastModified, headers)
            : new UpstreamRequest(new Uri(url), Headers: headers);

        for (int attempt = 0; ; attempt++)
        {
            UpstreamResponse response = await TimedSendAsync(request, url).ConfigureAwait(false);
            if (response.StatusCode != 429 || attempt >= policy.MaxRetries)
                return response;

            // Count each rate-limited response (the final, non-retried 429 is counted
            // in HandleUpstreamResponse — exactly one observation per response).
            _metrics.ObserveRateLimited(ProviderFor(url));
            TimeSpan wait = RetryDelay(response.RetryAfter, attempt, policy);
            _logger.LogWarning(
                "Upstream rate-limited for {Url}; retrying in {Wait:F1}s (attempt {Attempt}/{MaxRetries})",
                url, wait.TotalSeconds, attempt + 1, policy.MaxRetries);
            await Task.Delay(wait, CancellationToken.None).ConfigureAwait(false);
        }
    }

    /// <summary>Retry wait: Retry-After when given (past → immediate), else backoff base × 2^attempt, capped.</summary>
    private TimeSpan RetryDelay(DateTimeOffset? retryAfter, int attempt, CachePolicy policy)
    {
        TimeSpan wait = retryAfter is { } when
            ? when - _clock.UtcNow
            : TimeSpan.FromSeconds(policy.RetryBaseSeconds * Math.Pow(2, attempt));
        if (wait < TimeSpan.Zero)
            wait = TimeSpan.Zero;
        TimeSpan cap = policy.EffectiveMaxRetryDelay;
        return wait > cap ? cap : wait;
    }

    /// <summary>
    /// Sends one upstream request, recording its duration in the per-provider histogram
    /// (provider derived from the URL host). Recorded even when the request fails, so a
    /// failing provider is visible in the histogram too.
    /// </summary>
    private async Task<UpstreamResponse> TimedSendAsync(UpstreamRequest request, string url)
    {
        var sw = System.Diagnostics.Stopwatch.StartNew();
        try
        {
            return await _upstream.SendAsync(request, CancellationToken.None).ConfigureAwait(false);
        }
        finally
        {
            sw.Stop();
            _metrics.Observe(ProviderFor(url), sw.Elapsed.TotalSeconds);
        }
    }

    private static string ProviderFor(string url) => new Uri(url).Host switch
    {
        "api.themoviedb.org" => "tmdb",
        "image.tmdb.org" => "images",
        var host => host
    };

    private CachedResponse HandleUpstreamResponse(
        UpstreamResponse upstream, string key, string url, CachedUpstreamRow? cached, CachePolicy policy, DateTimeOffset now)
    {
        ObserveRateLimitHeaders(upstream.Headers);

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

        // 429 / 5xx / other: stale fallback or error. Count throttling explicitly —
        // TMDB's current API omits X-RateLimit-* headers, so 429s are the reliable
        // rate-limit signal for the /metrics/prometheus counter.
        if (upstream.StatusCode == 429)
            _metrics.ObserveRateLimited(ProviderFor(url));
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
        Interlocked.Increment(ref _hits);
        return cached.ToResponse(CacheSource.Stale);
    }

    /// <summary>Live hit/miss counters for /metrics (served-from-cache counts as a hit).</summary>
    public CacheCounters GetCounters() =>
        new(Interlocked.Read(ref _requests), Interlocked.Read(ref _hits));

    /// <summary>Reads TMDB's X-RateLimit-* headers (case-insensitive) into the metrics gauge.</summary>
    private void ObserveRateLimitHeaders(IReadOnlyDictionary<string, string>? headers)
    {
        if (headers is null)
            return;
        int? remaining = TryParseHeader(headers, "X-RateLimit-Remaining");
        int? limit = TryParseHeader(headers, "X-RateLimit-Limit");
        if (remaining is not null || limit is not null)
            _metrics.ObserveRateLimit(remaining, limit);
    }

    private static int? TryParseHeader(IReadOnlyDictionary<string, string> headers, string name) =>
        headers.TryGetValue(name, out string? value) && int.TryParse(value, out int parsed) ? parsed : null;
}
