namespace Metacache.Core.Providers;

/// <summary>
/// How the TMDB API key is presented to the API. TMDB's "API Read Access Token" goes in
/// an `Authorization: Bearer` header; the legacy v3 "API Key" must go in the `api_key`
/// query parameter. <see cref="TmdbAuthMode.Auto"/> probes once at first use and picks
/// the mode the key accepts.
/// </summary>
public enum TmdbAuthMode
{
    Auto,
    Bearer,
    Query
}

/// <summary>
/// Configuration for the TMDB client (DESIGN.md §7.2 TTL table, §15.5 flow).
/// In Bearer mode the key never appears in URLs, cache keys or logs; in Query mode
/// (legacy v3 keys) the cache key is still computed from the secret-free URL.
/// </summary>
public sealed record TmdbOptions(
    string ApiKey,
    string BaseUrl = "https://api.themoviedb.org/3",
    string ImageBaseUrl = "https://image.tmdb.org/t/p/original",
    TmdbAuthMode Auth = TmdbAuthMode.Auto);
