using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Metacache.Core;
using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Core.Providers;
using Metacache.Plex.Models;

namespace Metacache.Plex;

/// <summary>
/// Maps the Plex metadata-provider HTTP surface (DESIGN.md §6): provider definitions
/// (/movie, /tv), the match feature (POST /library/metadata/matches) and the metadata
/// feature (GET /library/metadata/{ratingKey} + /images). Status codes follow the
/// contract: 200, 400 (malformed/unsupported), 404 (unknown rating key), 500 (upstream
/// failure). M1 serves movie libraries; TV types return 400 until M2.
/// </summary>
public static class ProviderEndpoints
{
    public static void MapProviderEndpoints(this WebApplication app)
    {
        app.MapGet("/", () => Results.Text(
            "Metacache metadata provider. Definitions: GET /movie, GET /tv. Match: POST /library/metadata/matches. "
            + "Metadata: GET /library/metadata/{ratingKey}. Health: GET /healthz.",
            "text/plain"));

        app.MapGet("/movie", () => Results.Json(ProviderCatalog.Movie, ProviderJson.Options));
        app.MapGet("/tv", () => Results.Json(ProviderCatalog.Tv, ProviderJson.Options));

        app.MapPost("/library/metadata/matches", HandleMatch);
        app.MapGet("/library/metadata/{ratingKey}", HandleMetadata);
        app.MapGet("/library/metadata/{ratingKey}/images", HandleImages);
    }

    private static async Task<IResult> HandleMatch(HttpContext context, MovieProviderService movies)
    {
        string body = await new StreamReader(context.Request.Body).ReadToEndAsync(context.RequestAborted);
        if (!MatchRequestParser.TryParse(body, out MatchHint hint, out string? error))
            return Results.Json(new { error }, statusCode: StatusCodes.Status400BadRequest);

        hint = hint with { Language = PlexRequest.GetLanguage(context.Request) };
        try
        {
            MetadataContainer container = await movies.MatchAsync(hint, context.RequestAborted);
            return Results.Json(new MetadataContainerResponse(container), ProviderJson.Options);
        }
        catch (TmdbNotFoundException)
        {
            // A guid pointed at a movie that no longer exists upstream → no match.
            return Results.Json(new MetadataContainerResponse(
                new MetadataContainer(0, 0, ProviderIdentities.Movie, 0, [])), statusCode: StatusCodes.Status200OK);
        }
        catch (UpstreamException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
        }
        catch (TmdbConfigurationException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
        }
    }

    private static async Task<IResult> HandleMetadata(string ratingKey, HttpContext context, MovieProviderService movies)
    {
        if (!TryParseMovieKey(ratingKey, out string tmdbId))
            return Results.NotFound();

        string? language = PlexRequest.GetLanguage(context.Request);
        try
        {
            MetadataContainer? container = await movies.GetMovieMetadataAsync(tmdbId, language, context.RequestAborted);
            return container is null
                ? Results.NotFound()
                : Results.Json(new MetadataContainerResponse(container), ProviderJson.Options);
        }
        catch (TmdbNotFoundException)
        {
            return Results.NotFound();
        }
        catch (UpstreamException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
        }
        catch (TmdbConfigurationException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
        }
    }

    private static async Task<IResult> HandleImages(string ratingKey, HttpContext context, MovieProviderService movies)
    {
        if (!TryParseMovieKey(ratingKey, out string tmdbId))
            return Results.NotFound();

        string? language = PlexRequest.GetLanguage(context.Request);
        try
        {
            ImageContainer? container = await movies.GetMovieImagesAsync(tmdbId, language, context.RequestAborted);
            return container is null
                ? Results.NotFound()
                : Results.Json(new ImageContainerResponse(container), ProviderJson.Options);
        }
        catch (TmdbNotFoundException)
        {
            return Results.NotFound();
        }
        catch (UpstreamException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
        }
        catch (TmdbConfigurationException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: StatusCodes.Status500InternalServerError);
        }
    }

    /// <summary>M1 resolves only tmdb-sourced movie keys; everything else is unknown here.</summary>
    private static bool TryParseMovieKey(string ratingKey, out string tmdbId)
    {
        if (RatingKey.TryParse(ratingKey, out ParsedRatingKey? parsed)
            && parsed.Kind == "movie"
            && parsed.Source == "tmdb")
        {
            tmdbId = parsed.Id;
            return true;
        }
        tmdbId = "";
        return false;
    }
}
