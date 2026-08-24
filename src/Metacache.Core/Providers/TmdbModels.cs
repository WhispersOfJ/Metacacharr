using System.Text.Json.Serialization;

namespace Metacache.Core.Providers;

/// <summary>
/// Wire models for the TMDB v3 API responses Metacache consumes. The Plex mapper
/// works from these typed records, never from raw JSON.
/// </summary>
public sealed record TmdbSearchResponse(
    [property: JsonPropertyName("results")] IReadOnlyList<TmdbMovieSummary>? Results);

/// <summary>Compact movie shape returned by /search/movie and /find (no imdb_id).</summary>
public sealed record TmdbMovieSummary(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("title")] string? Title,
    [property: JsonPropertyName("original_title")] string? OriginalTitle,
    [property: JsonPropertyName("release_date")] string? ReleaseDate,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("poster_path")] string? PosterPath,
    [property: JsonPropertyName("backdrop_path")] string? BackdropPath,
    [property: JsonPropertyName("popularity")] double Popularity,
    [property: JsonPropertyName("adult")] bool Adult,
    [property: JsonPropertyName("original_language")] string? OriginalLanguage,
    [property: JsonPropertyName("vote_average")] double VoteAverage);

public sealed record TmdbFindResponse(
    [property: JsonPropertyName("movie_results")] IReadOnlyList<TmdbMovieSummary>? MovieResults);

/// <summary>Full movie object returned by GET /movie/{id} (includes imdb_id, genres, crew lists).</summary>
public sealed record TmdbMovie(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("imdb_id")] string? ImdbId,
    [property: JsonPropertyName("title")] string? Title,
    [property: JsonPropertyName("original_title")] string? OriginalTitle,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("tagline")] string? Tagline,
    [property: JsonPropertyName("release_date")] string? ReleaseDate,
    [property: JsonPropertyName("runtime")] int? Runtime,
    [property: JsonPropertyName("popularity")] double Popularity,
    [property: JsonPropertyName("adult")] bool Adult,
    [property: JsonPropertyName("vote_average")] double VoteAverage,
    [property: JsonPropertyName("poster_path")] string? PosterPath,
    [property: JsonPropertyName("backdrop_path")] string? BackdropPath,
    [property: JsonPropertyName("original_language")] string? OriginalLanguage,
    [property: JsonPropertyName("genres")] IReadOnlyList<TmdbNamedItem>? Genres,
    [property: JsonPropertyName("production_countries")] IReadOnlyList<TmdbCountry>? ProductionCountries,
    [property: JsonPropertyName("production_companies")] IReadOnlyList<TmdbNamedItem>? ProductionCompanies);

public sealed record TmdbNamedItem(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name);

public sealed record TmdbCountry(
    [property: JsonPropertyName("iso_3166_1")] string? Iso,
    [property: JsonPropertyName("name")] string? Name);
