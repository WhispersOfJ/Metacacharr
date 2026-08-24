using System.Net;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Metacache.Core.Cache;

namespace Metacache.Core.Providers;

/// <summary>Raised when the TVDB API key is missing/blank — configuration problem.</summary>
public sealed class TvdbConfigurationException : Exception
{
    public TvdbConfigurationException(string message) : base(message) { }
}

/// <summary>
/// Typed TVDB v4 client (DESIGN.md §15.9) — season/episode metadata as a fallback and
/// augmentation source behind TMDB.
///
/// Auth: TVDB v4 requires a bearer token from POST /v4/login (the key alone is not
/// accepted on data endpoints). The token is kept in memory only (~25 days) and the
/// login call is deliberately NOT routed through <see cref="UpstreamCache"/> — a
/// credential must never persist in the cache DB, matching the TMDB key-secrecy rule
/// (§16). A 401 from a data call (expired/revoked token) drops the token, logs in
/// again, and retries once.
///
/// Data: GET /v4/series/{id}/episodes/default returns the full series plus every
/// episode in one shot (no paging). It routes through the gateway like any other
/// upstream traffic — 24 h TTL, single-flight, ETag revalidation, stale-if-error —
/// with the token riding only in the Authorization header.
/// </summary>
public sealed class TvdbClient
{
    /// <summary>Series-episode payloads — 24 h like TMDB TV details.</summary>
    public static readonly CachePolicy EpisodesPolicy = new(TimeSpan.FromHours(24));

    /// <summary>In-memory login-token validity (TVDB tokens last ~1 month; stay conservative).</summary>
    private static readonly TimeSpan TokenTtl = TimeSpan.FromDays(25);

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly TvdbOptions _options;
    private readonly UpstreamCache _cache;
    private readonly HttpClient _http;
    private readonly IClock _clock;
    private readonly ILogger<TvdbClient> _logger;
    private readonly object _tokenLock = new();
    private readonly SemaphoreSlim _loginGate = new(1, 1);
    private string? _token;
    private DateTimeOffset _tokenExpiry;

    public TvdbClient(TvdbOptions options, UpstreamCache cache, HttpClient http, IClock clock, ILogger<TvdbClient> logger)
    {
        _options = options;
        _cache = cache;
        _http = http;
        _clock = clock;
        _logger = logger;
    }

    /// <summary>
    /// All season/episode metadata for one series. Returns null when the series is
    /// unknown to TVDB (404). Throws <see cref="TvdbConfigurationException"/> when no
    /// key is configured.
    /// </summary>
    public async Task<TvdbSeriesEpisodes?> GetSeriesEpisodesAsync(int seriesId, CancellationToken cancellationToken = default)
    {
        string url = $"{_options.BaseUrl.TrimEnd('/')}/v4/series/{seriesId}/episodes/default";

        try
        {
            return await FetchEpisodesAsync(url, cancellationToken).ConfigureAwait(false);
        }
        catch (UpstreamException ex) when (ex.StatusCode == 401)
        {
            // Stale or revoked token: drop it and retry exactly once after a fresh login.
            _logger.LogWarning("TVDB data call returned 401 — re-authenticating and retrying once");
            ClearToken();
            return await FetchEpisodesAsync(url, cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task<TvdbSeriesEpisodes?> FetchEpisodesAsync(string url, CancellationToken cancellationToken)
    {
        string token = await GetTokenAsync(cancellationToken).ConfigureAwait(false);
        var headers = new Dictionary<string, string> { ["Authorization"] = $"Bearer {token}" };
        CachedResponse response = await _cache
            .GetOrFetchAsync(url, EpisodesPolicy, cancellationToken, headers: headers)
            .ConfigureAwait(false);

        if (response.StatusCode == 404)
            return null;
        if (response.StatusCode is < 200 or >= 300)
            throw new UpstreamException(response.StatusCode, message: $"TVDB returned {response.StatusCode} for {url}");

        return JsonSerializer.Deserialize<TvdbSeriesEpisodesResponse>(response.Body, JsonOptions)?.Data;
    }

    /// <summary>Returns a valid login token, logging in on demand (cached in memory ~25 days).</summary>
    private async Task<string> GetTokenAsync(CancellationToken cancellationToken)
    {
        if (PeekToken() is { } current)
            return current;

        await _loginGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            // Double-checked: another caller may have logged in while we waited.
            if (PeekToken() is { } fresh)
                return fresh;

            if (string.IsNullOrWhiteSpace(_options.ApiKey))
                throw new TvdbConfigurationException(
                    "Metacache:Tvdb:ApiKey is not set. Add your TVDB v4 API key to configuration.");

            string token = await LoginAsync(cancellationToken).ConfigureAwait(false);
            lock (_tokenLock)
            {
                _token = token;
                _tokenExpiry = _clock.UtcNow.Add(TokenTtl);
            }
            return token;
        }
        finally
        {
            _loginGate.Release();
        }
    }

    private string? PeekToken()
    {
        lock (_tokenLock)
        {
            if (_token is not null && _tokenExpiry > _clock.UtcNow)
                return _token;
            return null;
        }
    }

    private void ClearToken()
    {
        lock (_tokenLock)
        {
            _token = null;
        }
    }

    /// <summary>POST /v4/login — never routed through the cache, so the bearer token never persists to disk.</summary>
    private async Task<string> LoginAsync(CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{_options.BaseUrl.TrimEnd('/')}/v4/login")
        {
            Content = new StringContent($$"""{"apikey":"{{_options.ApiKey}}"}""", Encoding.UTF8, "application/json")
        };
        using HttpResponseMessage response = await _http.SendAsync(request, cancellationToken).ConfigureAwait(false);
        if (response.StatusCode != HttpStatusCode.OK)
        {
            _logger.LogWarning("TVDB login failed with status {Status}", (int)response.StatusCode);
            throw new UpstreamException((int)response.StatusCode, message: $"TVDB login failed with status {(int)response.StatusCode}");
        }

        string body = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
        TvdbLoginResponse? login = JsonSerializer.Deserialize<TvdbLoginResponse>(body, JsonOptions);
        if (login?.Data?.Token is not { Length: > 0 } token)
            throw new UpstreamException(0, message: "TVDB login returned no token");
        return token;
    }
}
