using System.Text.Json.Serialization;

namespace Metacache.Core.Providers;

/// <summary>POST /v4/login response — the only TVDB call whose response is never cached (token secrecy).</summary>
public sealed record TvdbLoginResponse(
    [property: JsonPropertyName("data")] TvdbLoginData? Data);

public sealed record TvdbLoginData(
    [property: JsonPropertyName("token")] string? Token);

/// <summary>GET /v4/series/{id}/episodes/default response — full series plus every episode (no paging).</summary>
public sealed record TvdbSeriesEpisodesResponse(
    [property: JsonPropertyName("data")] TvdbSeriesEpisodes? Data);

public sealed record TvdbSeriesEpisodes(
    [property: JsonPropertyName("series")] TvdbSeries? Series,
    [property: JsonPropertyName("episodes")] IReadOnlyList<TvdbEpisode>? Episodes);

public sealed record TvdbSeries(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("firstAired")] string? FirstAired,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("image")] string? Image);

public sealed record TvdbEpisode(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("seriesId")] int SeriesId,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("aired")] string? Aired,
    [property: JsonPropertyName("number")] int Number,
    [property: JsonPropertyName("seasonNumber")] int SeasonNumber,
    [property: JsonPropertyName("image")] string? Image,
    [property: JsonPropertyName("runtime")] int? Runtime);
