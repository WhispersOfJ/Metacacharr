using Microsoft.AspNetCore.Http;

namespace Metacache.Plex;

/// <summary>
/// Request-context helpers for the provider API. Plex sends localization headers
/// (X-Plex-Language, X-Plex-Country) either as HTTP headers or query parameters
/// (see docs/API Endpoints.md "Common Request Headers").
/// </summary>
internal static class PlexRequest
{
    /// <summary>IETF language tag (e.g. "de-DE"), or null when the request carries none.</summary>
    public static string? GetLanguage(HttpRequest request)
    {
        if (request.Headers.TryGetValue("X-Plex-Language", out var header) && !string.IsNullOrEmpty(header))
            return header.ToString();

        foreach (var (key, value) in request.Query)
        {
            if (string.Equals(key, "X-Plex-Language", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrEmpty(value))
                return value.ToString();
        }
        return null;
    }

    /// <summary>ISO 3166-1 country code (e.g. "US"), or null when the request carries none.</summary>
    public static string? GetCountry(HttpRequest request)
    {
        if (request.Headers.TryGetValue("X-Plex-Country", out var header) && !string.IsNullOrEmpty(header))
            return header.ToString();

        foreach (var (key, value) in request.Query)
        {
            if (string.Equals(key, "X-Plex-Country", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrEmpty(value))
                return value.ToString();
        }
        return null;
    }
}
