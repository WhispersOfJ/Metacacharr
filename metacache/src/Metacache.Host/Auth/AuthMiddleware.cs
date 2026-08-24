using System.Security.Cryptography;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

namespace Metacache.Host.Auth;

/// <summary>
/// Bearer-token authentication middleware for protected endpoints (/admin/*, /webhook/*,
/// POST /warm/*). When <see cref="AuthOptions.ApiKey"/> is set, requests to protected
/// paths must include <c>Authorization: Bearer {key}</c>. An empty or null key disables
/// authentication (backward compatible with unauthenticated deployments).
/// </summary>
public sealed class AuthMiddleware
{
    private readonly RequestDelegate _next;
    private readonly AuthOptions _options;
    private readonly ILogger<AuthMiddleware> _logger;

    /// <summary>Path prefixes that require authentication.</summary>
    private static readonly string[] ProtectedPrefixes = ["/admin/", "/webhook/", "/warm/"];

    public AuthMiddleware(RequestDelegate next, AuthOptions options, ILogger<AuthMiddleware> logger)
    {
        _next = next;
        _options = options;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        if (RequiresAuth(context.Request) && !IsAuthenticated(context.Request))
        {
            _logger.LogDebug("Unauthorized {Method} {Path}", context.Request.Method, context.Request.Path);
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            context.Response.Headers["WWW-Authenticate"] = "Bearer";
            await context.Response.WriteAsJsonAsync(new { error = "Unauthorized. Provide a valid API key." })
                .ConfigureAwait(false);
            return;
        }

        await _next(context).ConfigureAwait(false);
    }

    /// <summary>
    /// Returns true if the request path requires authentication.
    /// POST /warm/* requires auth (triggers cache operations); GET /warm/status does not.
    /// GET /admin/* (read-only) and DELETE /admin/* both require auth.
    /// </summary>
    private bool RequiresAuth(HttpRequest request)
    {
        string path = request.Path.Value ?? "/";

        foreach (string prefix in ProtectedPrefixes)
        {
            if (!path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                continue;

            // /warm/status is public (read-only), POST /warm/* requires auth
            if (prefix == "/warm/")
            {
                return HttpMethods.IsPost(request.Method);
            }

            return true;
        }

        return false;
    }

    private bool IsAuthenticated(HttpRequest request)
    {
        // No key configured = auth disabled (backward compatible)
        if (string.IsNullOrEmpty(_options.ApiKey))
            return true;

        string? header = request.Headers.Authorization.FirstOrDefault();
        if (header is not null && header.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
        {
            string token = header["Bearer ".Length..].Trim();
            return CryptographicOperations.FixedTimeEquals(
                System.Text.Encoding.UTF8.GetBytes(token),
                System.Text.Encoding.UTF8.GetBytes(_options.ApiKey));
        }

        // Also accept X-API-Key header (some webhook callers don't use Authorization)
        if (request.Headers.TryGetValue("X-API-Key", out var apiKeyValues))
        {
            string? key = apiKeyValues.FirstOrDefault();
            if (key is not null)
            {
                return CryptographicOperations.FixedTimeEquals(
                    System.Text.Encoding.UTF8.GetBytes(key),
                    System.Text.Encoding.UTF8.GetBytes(_options.ApiKey));
            }
        }

        return false;
    }
}
