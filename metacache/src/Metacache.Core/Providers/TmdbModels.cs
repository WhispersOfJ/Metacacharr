using System.Text.Json.Serialization;

namespace Metacache.Core.Providers;

/// <summary>
/// Wire models for the TMDB v3 API responses Metacache consumes. The Plex mapper
/// works from these typed records, never from raw JSON.
/// </summary>

// ---- search / find ----

public sealed record TmdbSearchResponse(
    [property: JsonPropertyName("results")] IReadOnlyList<TmdbMovieSummary>? Results);

public sealed record TmdbTvSearchResponse(
    [property: JsonPropertyName("results")] IReadOnlyList<TmdbShowSummary>? Results);

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

/// <summary>Compact show shape returned by /search/tv and /find.</summary>
public sealed record TmdbShowSummary(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("original_name")] string? OriginalName,
    [property: JsonPropertyName("first_air_date")] string? FirstAirDate,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("poster_path")] string? PosterPath,
    [property: JsonPropertyName("backdrop_path")] string? BackdropPath,
    [property: JsonPropertyName("popularity")] double Popularity,
    [property: JsonPropertyName("adult")] bool Adult,
    [property: JsonPropertyName("original_language")] string? OriginalLanguage,
    [property: JsonPropertyName("vote_average")] double VoteAverage);

public sealed record TmdbFindResponse(
    [property: JsonPropertyName("movie_results")] IReadOnlyList<TmdbMovieSummary>? MovieResults,
    [property: JsonPropertyName("tv_results")] IReadOnlyList<TmdbShowSummary>? TvResults);

// ---- details ----

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

/// <summary>Full show object returned by GET /tv/{id}.</summary>
public sealed record TmdbShow(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("original_name")] string? OriginalName,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("first_air_date")] string? FirstAirDate,
    [property: JsonPropertyName("last_air_date")] string? LastAirDate,
    [property: JsonPropertyName("poster_path")] string? PosterPath,
    [property: JsonPropertyName("backdrop_path")] string? BackdropPath,
    [property: JsonPropertyName("popularity")] double Popularity,
    [property: JsonPropertyName("adult")] bool Adult,
    [property: JsonPropertyName("original_language")] string? OriginalLanguage,
    [property: JsonPropertyName("vote_average")] double VoteAverage,
    [property: JsonPropertyName("episode_run_time")] IReadOnlyList<int>? EpisodeRunTime,
    [property: JsonPropertyName("genres")] IReadOnlyList<TmdbNamedItem>? Genres,
    [property: JsonPropertyName("networks")] IReadOnlyList<TmdbNamedItem>? Networks,
    [property: JsonPropertyName("production_companies")] IReadOnlyList<TmdbNamedItem>? ProductionCompanies,
    [property: JsonPropertyName("production_countries")] IReadOnlyList<TmdbCountry>? ProductionCountries,
    [property: JsonPropertyName("seasons")] IReadOnlyList<TmdbSeasonSummary>? Seasons);

/// <summary>Season entry inside a show's `seasons` array (no episode list).</summary>
public sealed record TmdbSeasonSummary(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("season_number")] int SeasonNumber,
    [property: JsonPropertyName("episode_count")] int EpisodeCount,
    [property: JsonPropertyName("air_date")] string? AirDate,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("poster_path")] string? PosterPath);

/// <summary>Full season returned by GET /tv/{id}/season/{n} (includes episodes).</summary>
public sealed record TmdbSeason(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("season_number")] int SeasonNumber,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("air_date")] string? AirDate,
    [property: JsonPropertyName("poster_path")] string? PosterPath,
    [property: JsonPropertyName("episodes")] IReadOnlyList<TmdbEpisode>? Episodes);

public sealed record TmdbEpisode(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("overview")] string? Overview,
    [property: JsonPropertyName("episode_number")] int EpisodeNumber,
    [property: JsonPropertyName("season_number")] int SeasonNumber,
    [property: JsonPropertyName("air_date")] string? AirDate,
    [property: JsonPropertyName("still_path")] string? StillPath,
    [property: JsonPropertyName("runtime")] int? Runtime,
    [property: JsonPropertyName("vote_average")] double VoteAverage)
{
    /// <summary>True when adapted from TVDB (see TvdbMapper) so GUIDs stay honest.</summary>
    [JsonIgnore] public bool FromTvdb { get; init; }
}

// ---- credits / ratings / ids ----

public sealed record TmdbCredits(
    [property: JsonPropertyName("cast")] IReadOnlyList<TmdbCreditPerson>? Cast,
    [property: JsonPropertyName("crew")] IReadOnlyList<TmdbCreditPerson>? Crew);

public sealed record TmdbCreditPerson(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("character")] string? Character,
    [property: JsonPropertyName("job")] string? Job,
    [property: JsonPropertyName("department")] string? Department,
    [property: JsonPropertyName("profile_path")] string? ProfilePath,
    [property: JsonPropertyName("order")] int Order);

public sealed record TmdbReleaseDatesResponse(
    [property: JsonPropertyName("results")] IReadOnlyList<TmdbReleaseDateResult>? Results);

public sealed record TmdbReleaseDateResult(
    [property: JsonPropertyName("iso_3166_1")] string? Iso,
    [property: JsonPropertyName("release_dates")] IReadOnlyList<TmdbReleaseDate>? ReleaseDates);

public sealed record TmdbReleaseDate(
    [property: JsonPropertyName("certification")] string? Certification);

public sealed record TmdbContentRatingsResponse(
    [property: JsonPropertyName("results")] IReadOnlyList<TmdbContentRating>? Results);

public sealed record TmdbContentRating(
    [property: JsonPropertyName("iso_3166_1")] string? Iso,
    [property: JsonPropertyName("rating")] string? Rating);

public sealed record TmdbExternalIds(
    [property: JsonPropertyName("imdb_id")] string? ImdbId,
    [property: JsonPropertyName("tvdb_id")] int? TvdbId);

public sealed record TmdbNamedItem(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string? Name);

public sealed record TmdbCountry(
    [property: JsonPropertyName("iso_3166_1")] string? Iso,
    [property: JsonPropertyName("name")] string? Name);
