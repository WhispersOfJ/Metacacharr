using System.Text.Json;
using Metacache.Core.Cache;

namespace Metacache.Core.Providers;

/// <summary>
/// M3 warm-up client for the ARR apps (DESIGN.md §8): Radarr's /api/v3/movie and
/// Sonarr's /api/v3/series become the inventory Metacache pre-populates. The API
/// key rides in the X-Api-Key header (never in URLs or cache keys). These calls
/// are deliberately NOT routed through the upstream cache — the ARR APIs are the
/// inventory source and change constantly; they are queried on demand.
/// </summary>
public sealed class ArrClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly string _baseUrl;
    private readonly string _apiKey;
    private readonly IUpstreamHttp _http;

    public ArrClient(string baseUrl, string apiKey, IUpstreamHttp http)
    {
        _baseUrl = Normalize(baseUrl);
        _apiKey = apiKey;
        _http = http;
    }

    /// <summary>All movies in the Radarr library.</summary>
    public async Task<IReadOnlyList<ArrMovie>> GetMoviesAsync(CancellationToken cancellationToken = default)
    {
        using JsonDocument doc = await GetJsonAsync("/api/v3/movie", cancellationToken).ConfigureAwait(false);
        var movies = new List<ArrMovie>();
        foreach (JsonElement e in doc.RootElement.EnumerateArray())
        {
            movies.Add(new ArrMovie(
                e.GetProperty("id").GetInt32(),
                GetString(e, "title"),
                GetNullableInt(e, "tmdbId"),
                GetNullableInt(e, "year")));
        }
        return movies;
    }

    /// <summary>All series in the Sonarr library.</summary>
    public async Task<IReadOnlyList<ArrSeries>> GetSeriesAsync(CancellationToken cancellationToken = default)
    {
        using JsonDocument doc = await GetJsonAsync("/api/v3/series", cancellationToken).ConfigureAwait(false);
        var series = new List<ArrSeries>();
        foreach (JsonElement e in doc.RootElement.EnumerateArray())
        {
            series.Add(new ArrSeries(
                e.GetProperty("id").GetInt32(),
                GetString(e, "title"),
                GetNullableInt(e, "tvdbId"),
                GetNullableInt(e, "year")));
        }
        return series;
    }

    private async Task<JsonDocument> GetJsonAsync(string path, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(_baseUrl))
            throw new ArrConfigurationException("ARR base URL is not set (Metacache:Arr:RadarrUrl / SonarrUrl).");
        if (string.IsNullOrWhiteSpace(_apiKey))
            throw new ArrConfigurationException("ARR API key is not set (Metacache:Arr:RadarrApiKey / SonarrApiKey).");

        var request = new UpstreamRequest(new Uri($"{_baseUrl}{path}"),
            Headers: new Dictionary<string, string> { ["X-Api-Key"] = _apiKey });
        UpstreamResponse response = await _http.SendAsync(request, cancellationToken).ConfigureAwait(false);
        if (response.StatusCode is < 200 or >= 300)
            throw new ArrException(response.StatusCode, $"ARR API returned {response.StatusCode} for {path}");

        return JsonDocument.Parse(response.Body);
    }

    private static string Normalize(string baseUrl)
    {
        baseUrl = (baseUrl ?? string.Empty).Trim().TrimEnd('/');
        return baseUrl;
    }

    private static string? GetString(JsonElement element, string name) =>
        element.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static int? GetNullableInt(JsonElement element, string name) =>
        element.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.Number
            && value.TryGetInt32(out int parsed)
            ? parsed
            : null;
}

/// <summary>Raised when the ARR app returned an error status.</summary>
public sealed class ArrException : Exception
{
    public int StatusCode { get; }

    public ArrException(int statusCode, string message) : base(message)
    {
        StatusCode = statusCode;
    }
}

/// <summary>Raised when ARR configuration is missing.</summary>
public sealed class ArrConfigurationException : Exception
{
    public ArrConfigurationException(string message) : base(message)
    {
    }
}
