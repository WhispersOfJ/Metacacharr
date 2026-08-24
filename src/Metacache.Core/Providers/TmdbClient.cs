using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Metacache.Core.Cache;

namespace Metacache.Core.Providers;

/// <summary>Raised when a TMDB resource does not exist (upstream 404).</summary>
public sealed class TmdbNotFoundException : Exception
{
    public TmdbNotFoundException(string message) : base(message) { }
}

/// <summary>Raised when the TMDB API key is missing/blank — configuration problem.</summary>
public sealed class TmdbConfigurationException : Exception
{
    public TmdbConfigurationException(string message) : base(message) { }
}

/// <summary>
/// Typed TMDB v3 client (DESIGN.md §15.5 step 2). Every call routes through
/// <see cref="UpstreamCache"/>, so search and details are single-flighted, TTL'd,
/// ETag-revalidated and stale-if-error served exactly like any other upstream traffic
/// (§7.2: search 12 h, item JSON 24 h).
///
/// Auth (§16): TMDB's API Read Access Token is sent as `Authorization: Bearer` (the
/// key then never appears in URLs, cache keys or logs). Legacy v3 API keys only work
/// as the `api_key` query parameter — in that mode the cache key is computed from the
/// secret-free URL via <see cref="UpstreamCache"/>'s cacheKey override, so the key
/// still never lands in the cache DB. <see cref="TmdbAuthMode.Auto"/> (default) probes
/// once per process and picks whichever the key accepts.
/// </summary>
public sealed class TmdbClient
{
    public static readonly CachePolicy SearchPolicy = new(TimeSpan.FromHours(12));
    public static readonly CachePolicy MoviePolicy = new(TimeSpan.FromHours(24));

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly TmdbOptions _options;
    private readonly UpstreamCache _cache;
    private readonly ILogger<TmdbClient> _logger;
    private readonly IReadOnlyDictionary<string, string> _bearerHeaders;
    private readonly object _modeLock = new();
    private Task<TmdbAuthMode>? _modeTask;

    public TmdbClient(TmdbOptions options, UpstreamCache cache, ILogger<TmdbClient> logger)
    {
        _options = options;
        _cache = cache;
        _logger = logger;
        _bearerHeaders = string.IsNullOrWhiteSpace(options.ApiKey)
            ? new Dictionary<string, string>()
            : new Dictionary<string, string> { ["Authorization"] = $"Bearer {options.ApiKey}" };
    }

    /// <summary>Full image URL for a TMDB image path (e.g. "/p4.jpg"), or null for empty paths.</summary>
    public string? ImageUrl(string? path) =>
        string.IsNullOrEmpty(path) ? null : $"{_options.ImageBaseUrl.TrimEnd('/')}{path}";

    /// <summary>Searches movies by title, optionally narrowed by release year.</summary>
    public async Task<IReadOnlyList<TmdbMovieSummary>> SearchMoviesAsync(
        string query, int? year, string? language, bool includeAdult, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(query);

        var queryParams = new Dictionary<string, string?>
        {
            ["query"] = query,
            ["language"] = language ?? "en-US",
            ["include_adult"] = includeAdult ? "true" : "false",
            ["page"] = "1"
        };
        if (year is { } y)
            queryParams["year"] = y.ToString(CultureInfo.InvariantCulture);

        string url = BuildUrl("/search/movie", queryParams);
        TmdbSearchResponse? response = await GetJsonAsync<TmdbSearchResponse>(url, SearchPolicy, cancellationToken)
            .ConfigureAwait(false);
        return response?.Results ?? [];
    }

    /// <summary>Full details for one movie (imdb id, genres, companies, runtime, artwork).</summary>
    public async Task<TmdbMovie> GetMovieAsync(int id, string? language, CancellationToken cancellationToken = default)
    {
        var queryParams = new Dictionary<string, string?> { ["language"] = language ?? "en-US" };
        string url = BuildUrl($"/movie/{id}", queryParams);
        TmdbMovie? movie = await GetJsonAsync<TmdbMovie>(url, MoviePolicy, cancellationToken).ConfigureAwait(false);
        if (movie is null)
            throw new TmdbNotFoundException($"TMDB movie {id} not found");
        return movie;
    }

    /// <summary>
    /// Resolves an external id (imdb/tvdb) to TMDB movies. Used for exact GUID pinning
    /// when a match request carries e.g. "imdb://tt0088763" (§15.5 step 2).
    /// </summary>
    public async Task<IReadOnlyList<TmdbMovieSummary>> FindByExternalIdAsync(
        string externalSource, string externalId, string? language, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(externalSource);
        ArgumentException.ThrowIfNullOrWhiteSpace(externalId);

        var queryParams = new Dictionary<string, string?>
        {
            ["external_source"] = externalSource,
            ["language"] = language ?? "en-US"
        };
        string url = BuildUrl($"/find/{Uri.EscapeDataString(externalId)}", queryParams);
        TmdbFindResponse? response = await GetJsonAsync<TmdbFindResponse>(url, SearchPolicy, cancellationToken)
            .ConfigureAwait(false);
        return response?.MovieResults ?? [];
    }

    private async Task<T?> GetJsonAsync<T>(string url, CachePolicy policy, CancellationToken cancellationToken)
        where T : class
    {
        if (string.IsNullOrWhiteSpace(_options.ApiKey))
            throw new TmdbConfigurationException(
                "Metacache:Tmdb:ApiKey is not set. Add your TMDB API Read Access Token (or v3 API key) to configuration.");

        TmdbAuthMode mode = await ResolveAuthModeAsync().ConfigureAwait(false);

        string requestUrl = url;
        string? cacheKey = null;
        IReadOnlyDictionary<string, string>? headers = null;
        if (mode == TmdbAuthMode.Query)
        {
            // Key rides in the URL, but the cache key is the secret-free URL.
            cacheKey = UpstreamCache.ComputeKey(url);
            requestUrl = $"{url}&api_key={Uri.EscapeDataString(_options.ApiKey)}";
        }
        else
        {
            headers = _bearerHeaders;
        }

        CachedResponse response = await _cache
            .GetOrFetchAsync(requestUrl, policy, cancellationToken, headers: headers, cacheKey: cacheKey)
            .ConfigureAwait(false);

        if (response.StatusCode == 404)
            throw new TmdbNotFoundException(url);
        if (response.StatusCode is < 200 or >= 300)
            throw new UpstreamException(response.StatusCode, message: $"TMDB returned {response.StatusCode} for {url}");

        return JsonSerializer.Deserialize<T>(response.Body, JsonOptions);
    }

    /// <summary>Resolves the auth mode: explicit config wins; Auto probes once (cached per process).</summary>
    private Task<TmdbAuthMode> ResolveAuthModeAsync()
    {
        if (_options.Auth != TmdbAuthMode.Auto)
            return Task.FromResult(_options.Auth);

        lock (_modeLock)
        {
            _modeTask ??= ProbeAuthModeAsync();
        }

        return AwaitModeAsync();
    }

    private async Task<TmdbAuthMode> AwaitModeAsync()
    {
        try
        {
            return await _modeTask!.ConfigureAwait(false);
        }
        catch
        {
            // A failed probe must not poison the process: retry on the next request.
            lock (_modeLock)
            {
                _modeTask = null;
            }
            throw;
        }
    }

    /// <summary>Probes /authentication with Bearer; a 401 means the key is a legacy v3 key → Query mode.</summary>
    private async Task<TmdbAuthMode> ProbeAuthModeAsync()
    {
        string url = BuildUrl("/authentication", query: null);
        try
        {
            await _cache.GetOrFetchAsync(url, SearchPolicy, headers: _bearerHeaders).ConfigureAwait(false);
            _logger.LogInformation("TMDB API key accepted via Authorization: Bearer");
            return TmdbAuthMode.Bearer;
        }
        catch (UpstreamException ex) when (ex.StatusCode == 401)
        {
            _logger.LogInformation("TMDB API key rejected as Bearer (legacy v3 key?) — using api_key query param");
            return TmdbAuthMode.Query;
        }
    }

    /// <summary>Builds a normalized URL: sorted query params, URI-escaped, no API key.</summary>
    private string BuildUrl(string path, IReadOnlyDictionary<string, string?>? query)
    {
        string baseUrl = _options.BaseUrl.TrimEnd('/');
        if (query is null || query.Count == 0)
            return $"{baseUrl}{path}";

        string queryString = string.Join('&', query
            .OrderBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv => kv.Value is null
                ? Uri.EscapeDataString(kv.Key)
                : $"{Uri.EscapeDataString(kv.Key)}={Uri.EscapeDataString(kv.Value)}"));
        return $"{baseUrl}{path}?{queryString}";
    }
}
