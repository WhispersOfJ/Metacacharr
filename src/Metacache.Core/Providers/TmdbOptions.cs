namespace Metacache.Core.Providers;

/// <summary>
/// Configuration for the TMDB client (DESIGN.md §7.2 TTL table, §15.5 flow).
/// The API key is sent as an `Authorization: Bearer` header (TMDB v3 accepts the
/// API Read Access Token there), so it never appears in URLs — keeping cache keys
/// and logs free of secrets.
/// </summary>
public sealed record TmdbOptions(
    string ApiKey,
    string BaseUrl = "https://api.themoviedb.org/3",
    string ImageBaseUrl = "https://image.tmdb.org/t/p/original");
