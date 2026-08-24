using System.Globalization;
using Microsoft.Extensions.Logging;
using Metacache.Core;
using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Core.Providers;
using Metacache.Plex.Mappers;
using Metacache.Plex.Models;

namespace Metacache.Plex;

/// <summary>
/// Movie half of the provider logic (DESIGN.md §15.5): resolves a match hint to TMDB
/// candidates (external-guid pin or title search), scores them with the pure
/// <see cref="MatchScorer"/>, enriches the winners through the cache-backed TMDB
/// client, and maps to Plex containers. Metadata + images endpoints resolve a movie
/// rating key and map the details.
/// </summary>
public sealed class MovieProviderService
{
    /// <summary>How many ranked candidates are enriched with details for a manual (Fix Match) search.</summary>
    private const int ManualEnrichDepth = 8;

    private readonly TmdbClient _tmdb;
    private readonly TmdbOptions _options;
    private readonly MatchPolicy _policy;
    private readonly ImageCache _images;
    private readonly ILogger<MovieProviderService> _logger;

    public MovieProviderService(
        TmdbClient tmdb, TmdbOptions options, MatchPolicy policy, ImageCache images, ILogger<MovieProviderService> logger)
    {
        _tmdb = tmdb;
        _options = options;
        _policy = policy;
        _images = images;
        _logger = logger;
    }

    public async Task<MetadataContainer> MatchAsync(MatchHint hint, CancellationToken cancellationToken)
    {
        IReadOnlyList<MatchCandidate> candidates = await ResolveCandidatesAsync(hint, cancellationToken);
        IReadOnlyList<ScoredMatch> scored = MatchScorer.Score(hint, candidates, _policy);

        if (hint.Manual)
            return await BuildManualContainerAsync(hint, scored, cancellationToken);

        ScoredMatch? best = scored.FirstOrDefault();
        if (best is null)
        {
            _logger.LogInformation("Movie match for '{Title}' cleared no candidate (auto threshold {Threshold})",
                hint.Title, _policy.AutoMatchThreshold);
            return Empty();
        }

        TmdbMovie movie = await _tmdb.GetMovieAsync(IdOf(best.Candidate.Id), hint.Language, cancellationToken);
        RegisterImages(movie);
        _logger.LogInformation("Auto-matched '{Title}' → tmdb {Id} (score {Score:F2})", hint.Title, movie.Id, best.Score);
        return new MetadataContainer(0, 1, ProviderIdentities.Movie, 1,
            [MovieMapper.ToMatchItem(movie, ProviderIdentities.Movie, _options.ImageBaseUrl, hint.Language)]);
    }

    /// <summary>Full metadata for a movie rating key; null when the id is malformed or the movie is unknown.</summary>
    public async Task<MetadataContainer?> GetMovieMetadataAsync(
        string tmdbId, string? language, CancellationToken cancellationToken)
    {
        if (!int.TryParse(tmdbId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbMovie movie = await _tmdb.GetMovieAsync(id, language, cancellationToken);
        RegisterImages(movie);
        var item = MovieMapper.ToMetadata(movie, ProviderIdentities.Movie, _options.ImageBaseUrl, language);
        return new MetadataContainer(0, 1, ProviderIdentities.Movie, 1, [item]);
    }

    /// <summary>All image assets for a movie; null when the rating key cannot resolve.</summary>
    public async Task<ImageContainer?> GetMovieImagesAsync(
        string tmdbId, string? language, CancellationToken cancellationToken)
    {
        if (!int.TryParse(tmdbId, NumberStyles.None, CultureInfo.InvariantCulture, out int id))
            return null;

        TmdbMovie movie = await _tmdb.GetMovieAsync(id, language, cancellationToken);
        RegisterImages(movie);
        IReadOnlyList<ImageAsset> images = MovieMapper.BuildImages(movie, _options.ImageBaseUrl) ?? [];
        return new ImageContainer(0, images.Count, ProviderIdentities.Movie, images.Count, images);
    }

    private async Task<IReadOnlyList<MatchCandidate>> ResolveCandidatesAsync(MatchHint hint, CancellationToken cancellationToken)
    {
        if (hint.ExternalGuids.Count > 0)
        {
            foreach (string guid in hint.ExternalGuids)
            {
                if (!ExternalGuid.TryParse(guid, out string source, out string id))
                    continue;

                if (source == "tmdb" && int.TryParse(id, NumberStyles.None, CultureInfo.InvariantCulture, out int tmdbId))
                    return [CandidateFrom(await _tmdb.GetMovieAsync(tmdbId, hint.Language, cancellationToken))];

                if (source is "imdb" or "tvdb")
                {
                    string externalSource = source == "imdb" ? "imdb_id" : "tvdb_id";
                    IReadOnlyList<TmdbMovieSummary> found =
                        await _tmdb.FindByExternalIdAsync(externalSource, id, hint.Language, cancellationToken);
                    if (found.Count == 0)
                        continue;

                    // Enrich the top hit so the exact-GUID override can fire and Guid[] is complete.
                    TmdbMovie top = await _tmdb.GetMovieAsync(found[0].Id, hint.Language, cancellationToken);
                    return [CandidateFrom(top)];
                }
            }
            return []; // guid supplied but unresolvable → no candidates
        }

        if (string.IsNullOrWhiteSpace(hint.Title))
            return [];

        IReadOnlyList<TmdbMovieSummary> search = await _tmdb
            .SearchMoviesAsync(hint.Title, hint.Year, hint.Language, hint.IncludeAdult, cancellationToken);
        return search.Select(CandidateFrom).ToList();
    }

    private async Task<MetadataContainer> BuildManualContainerAsync(
        MatchHint hint, IReadOnlyList<ScoredMatch> scored, CancellationToken cancellationToken)
    {
        IReadOnlyList<ScoredMatch> top = scored.Take(ManualEnrichDepth).ToList();
        TmdbMovie[] movies = await Task.WhenAll(top.Select(s => _tmdb.GetMovieAsync(IdOf(s.Candidate.Id), hint.Language, cancellationToken)));
        foreach (TmdbMovie movie in movies)
            RegisterImages(movie);
        var items = movies
            .Select(m => MovieMapper.ToMatchItem(m, ProviderIdentities.Movie, _options.ImageBaseUrl, hint.Language))
            .ToList();
        _logger.LogInformation("Manual movie search '{Title}' returned {Count} ranked candidates", hint.Title, items.Count);
        return new MetadataContainer(0, items.Count, ProviderIdentities.Movie, items.Count, items);
    }

    private static MetadataContainer Empty() =>
        new(0, 0, ProviderIdentities.Movie, 0, []);

    /// <summary>
    /// Tells the image cache about this movie's artwork so the /img/{hash} URLs the
    /// mapper emits resolve on Plex's first request (fetch happens lazily then).
    /// </summary>
    private void RegisterImages(TmdbMovie movie)
    {
        if (_tmdb.ImageUrl(movie.PosterPath) is { } poster)
            _images.RegisterUrl(poster);
        if (_tmdb.ImageUrl(movie.BackdropPath) is { } backdrop)
            _images.RegisterUrl(backdrop);
    }

    private static MatchCandidate CandidateFrom(TmdbMovieSummary summary) => new(
        Id: summary.Id.ToString(CultureInfo.InvariantCulture),
        Title: string.IsNullOrEmpty(summary.Title) ? summary.OriginalTitle ?? string.Empty : summary.Title,
        OriginalTitle: summary.OriginalTitle,
        Year: MovieYear(summary.ReleaseDate),
        OriginalLanguage: summary.OriginalLanguage,
        Popularity: summary.Popularity,
        Adult: summary.Adult,
        ExternalIds: [$"tmdb://{summary.Id}"]);

    private static MatchCandidate CandidateFrom(TmdbMovie movie)
    {
        var ids = new List<string> { $"tmdb://{movie.Id}" };
        if (!string.IsNullOrEmpty(movie.ImdbId))
            ids.Add($"imdb://{movie.ImdbId}");
        return new MatchCandidate(
            Id: movie.Id.ToString(CultureInfo.InvariantCulture),
            Title: string.IsNullOrEmpty(movie.Title) ? movie.OriginalTitle ?? string.Empty : movie.Title,
            OriginalTitle: movie.OriginalTitle,
            Year: MovieYear(movie.ReleaseDate),
            OriginalLanguage: movie.OriginalLanguage,
            Popularity: movie.Popularity,
            Adult: movie.Adult,
            ExternalIds: ids);
    }

    private static int IdOf(string id) => int.Parse(id, CultureInfo.InvariantCulture);

    private static int? MovieYear(string? releaseDate)
    {
        if (releaseDate is null || releaseDate.Length < 4)
            return null;
        return int.TryParse(releaseDate.AsSpan(0, 4), NumberStyles.None, CultureInfo.InvariantCulture, out int year)
            ? year
            : null;
    }
}
