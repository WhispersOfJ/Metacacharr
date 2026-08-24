using System.Net;
using Metacache.Core.Cache;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

namespace Metacache.Host.Proxy;

/// <summary>
/// Middleware that intercepts HTTP/HTTPS requests arriving via DNS override, reconstructs
/// the original upstream URL from the SNI hostname + path + query, fetches through the
/// <see cref="UpstreamCache"/>, and returns the response. This makes ARR apps (Sonarr,
/// Radarr) hit the local cache transparently — they never know they're not talking to
/// the real API.
/// </summary>
public sealed class ProxyMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ProxyRouter _router;
    private readonly UpstreamCache _cache;
    private readonly ILogger<ProxyMiddleware> _logger;

    /// <summary>
    /// Default proxy cache policy — 12 h TTL, stale-if-error, two 429 retries.
    /// Matches the metadata TTL in DESIGN.md §7.2.
    /// </summary>
    private static readonly CachePolicy DefaultPolicy = new(
        Ttl: TimeSpan.FromHours(12),
        ServeStaleOnError: true,
        MaxRetries: 2,
        RetryBaseSeconds: 2.0);

    public ProxyMiddleware(
        RequestDelegate next,
        ProxyRouter router,
        UpstreamCache cache,
        ILogger<ProxyMiddleware> logger)
    {
        _next = next;
        _router = router;
        _cache = cache;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        // The SNI hostname is what the client (ARR app) thinks it's talking to.
        string? sniHostname = context.Request.Host.Host;
        if (sniHostname is null)
        {
            context.Response.StatusCode = StatusCodes.Status421MisdirectedRequest;
            return;
        }

        string? upstream = _router.Resolve(sniHostname);
        if (upstream is null)
        {
            // Unknown hostname — not in our route table. Pass through to normal
            // ASP.NET routing (the provider endpoints, admin, etc.).
            await _next(context).ConfigureAwait(false);
            return;
        }

        // Reconstruct the full upstream URL so the cache key matches what a direct
        // call would produce.
        string originalUrl = _router.ReconstructUrl(
            sniHostname, context.Request.Path, context.Request.QueryString);

        // Pass through the original headers (Authorization, Accept, etc.) — ARR apps
        // send their own API keys and the upstream needs them.
        var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var header in context.Request.Headers)
        {
            // Skip hop-by-hop headers
            if (header.Key.Equals("Host", StringComparison.OrdinalIgnoreCase))
                continue;
            headers[header.Key] = string.Join(", ", header.Value!);
        }

        // The API key may be in the Authorization header or the query string.
        // UpstreamCache.ComputeKey hashes the full URL; if the API key is in the URL,
        // we strip it for the cache key so secrets don't leak into the DB.
        string? cacheKey = null;
        if (context.Request.Query.ContainsKey("api_key"))
        {
            // Rebuild URL without api_key for the cache key
            var cleanedUri = new Uri(originalUrl);
            var queryParts = new List<string>();
            foreach (string key in context.Request.Query.Keys)
            {
                if (key == "api_key") continue;
                foreach (string? val in context.Request.Query[key])
                    queryParts.Add($"{Uri.EscapeDataString(key)}={Uri.EscapeDataString(val ?? "")}");
            }
            string cleanedQs = queryParts.Count > 0 ? "?" + string.Join("&", queryParts) : "";
            cacheKey = UpstreamCache.ComputeKey($"{cleanedUri.Scheme}://{cleanedUri.Host}{cleanedUri.AbsolutePath}{cleanedQs}");
        }

        try
        {
            CachedResponse response = await _cache.GetOrFetchAsync(
                originalUrl, DefaultPolicy, context.RequestAborted, headers, cacheKey).ConfigureAwait(false);

            context.Response.StatusCode = response.StatusCode;
            if (response.ContentType is not null)
                context.Response.ContentType = response.ContentType;

            // Pass through cache metadata as headers for debugging
            context.Response.Headers["X-Cache-Source"] = response.Source.ToString();

            if (response.Body.Length > 0)
                await context.Response.Body.WriteAsync(response.Body, context.RequestAborted).ConfigureAwait(false);
        }
        catch (UpstreamException ex)
        {
            _logger.LogWarning(ex, "Proxy upstream failure for {Hostname}{Path}", sniHostname, context.Request.Path);
            context.Response.StatusCode = ex.StatusCode > 0 ? ex.StatusCode : StatusCodes.Status502BadGateway;
            await context.Response.WriteAsJsonAsync(new
            {
                error = ex.Message,
                statusCode = ex.StatusCode
            }, context.RequestAborted).ConfigureAwait(false);
        }
    }
}
