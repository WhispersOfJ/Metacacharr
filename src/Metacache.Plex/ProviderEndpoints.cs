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
/// (/movie, /tv), the match feature (POST /library/metadata/matches), the metadata
/// feature (GET /library/metadata/{ratingKey} + /images), and the hierarchy endpoints
/// (/children, /grandchildren — paged via X-Plex-Container-Size/Start). M2 serves
/// movies, shows, seasons and episodes. Status codes: 200, 400 (malformed), 404
/// (unknown rating key / upstream 404), 500 (upstream failure).
/// </summary>
public static class ProviderEndpoints
{
    public static void MapProviderEndpoints(this WebApplication app)
    {
        app.MapGet("/", () => Results.Text(
            "Metacache metadata provider. Definitions: GET /movie, GET /tv. Match: POST /library/metadata/matches. "
            + "Metadata: GET /library/metadata/{ratingKey}. Dashboard: GET /dashboard. Metrics: GET /metrics. "
            + "Health: GET /healthz.",
            "text/plain"));

        app.MapGet("/movie", () => Results.Json(ProviderCatalog.Movie, ProviderJson.Options));
        app.MapGet("/tv", () => Results.Json(ProviderCatalog.Tv, ProviderJson.Options));

        app.MapPost("/library/metadata/matches", HandleMatch);
        app.MapGet("/library/metadata/{ratingKey}", HandleMetadata);
        app.MapGet("/library/metadata/{ratingKey}/children", HandleChildren);
        app.MapGet("/library/metadata/{ratingKey}/grandchildren", HandleGrandchildren);
        app.MapGet("/library/metadata/{ratingKey}/images", HandleImages);
    }

    private static async Task<IResult> HandleMatch(HttpContext context, MovieProviderService movies, TvProviderService tv)
    {
        string body = await new StreamReader(context.Request.Body).ReadToEndAsync(context.RequestAborted);
        if (!MatchRequestParser.TryParse(body, out MatchHint hint, out bool includeChildren, out string? error))
            return Results.Json(new { error }, statusCode: StatusCodes.Status400BadRequest);

        hint = hint with { Language = PlexRequest.GetLanguage(context.Request) };
        try
        {
            MetadataContainer container = hint.Kind == MatchKind.Movie
                ? await movies.MatchAsync(hint, context.RequestAborted)
                : await tv.MatchAsync(hint, includeChildren, context.RequestAborted);
            return Results.Json(new MetadataContainerResponse(container), ProviderJson.Options);
        }
        catch (TmdbNotFoundException)
        {
            // A guid pointed at something that no longer exists upstream → no match.
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

    private static async Task<IResult> HandleMetadata(
        string ratingKey, HttpContext context, MovieProviderService movies, TvProviderService tv)
    {
        if (!TryParseTmdbKey(ratingKey, out ParsedRatingKey parsed))
            return Results.NotFound();

        string? language = PlexRequest.GetLanguage(context.Request);
        string? country = PlexRequest.GetCountry(context.Request);
        bool includeChildren = string.Equals(context.Request.Query["includeChildren"], "1");

        try
        {
            MetadataContainer? container = parsed.Kind switch
            {
                "movie" => await movies.GetMovieMetadataAsync(parsed.Id, language, country, context.RequestAborted),
                "show" => await tv.GetShowMetadataAsync(parsed.Id, includeChildren, language, country, context.RequestAborted),
                "season" when parsed.Indices.Length == 1 => await tv.GetSeasonMetadataAsync(
                    parsed.Id, parsed.Indices[0], includeChildren, language, country, context.RequestAborted),
                "episode" when parsed.Indices.Length == 2 => await tv.GetEpisodeMetadataAsync(
                    parsed.Id, parsed.Indices[0], parsed.Indices[1], language, context.RequestAborted),
                _ => null
            };
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

    private static async Task<IResult> HandleChildren(
        string ratingKey, HttpContext context, TvProviderService tv)
    {
        if (!TryParseTmdbKey(ratingKey, out ParsedRatingKey parsed))
            return Results.NotFound();

        string? language = PlexRequest.GetLanguage(context.Request);
        try
        {
            MetadataContainer? container = parsed.Kind switch
            {
                "show" => await tv.GetShowChildrenAsync(parsed.Id, language, context.Request, context.RequestAborted),
                "season" when parsed.Indices.Length == 1 => await tv.GetSeasonChildrenAsync(
                    parsed.Id, parsed.Indices[0], language, context.Request, context.RequestAborted),
                _ => null
            };
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

    private static async Task<IResult> HandleGrandchildren(
        string ratingKey, HttpContext context, TvProviderService tv)
    {
        if (!TryParseTmdbKey(ratingKey, out ParsedRatingKey parsed))
            return Results.NotFound();

        string? language = PlexRequest.GetLanguage(context.Request);
        try
        {
            MetadataContainer? container = parsed.Kind switch
            {
                "show" => await tv.GetShowGrandchildrenAsync(parsed.Id, language, context.Request, context.RequestAborted),
                "season" when parsed.Indices.Length == 1 => await tv.GetSeasonChildrenAsync(
                    parsed.Id, parsed.Indices[0], language, context.Request, context.RequestAborted),
                _ => null
            };
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

    private static async Task<IResult> HandleImages(
        string ratingKey, HttpContext context, MovieProviderService movies, TvProviderService tv)
    {
        if (!TryParseTmdbKey(ratingKey, out ParsedRatingKey parsed))
            return Results.NotFound();

        string? language = PlexRequest.GetLanguage(context.Request);
        try
        {
            ImageContainer? container = parsed.Kind switch
            {
                "movie" => await movies.GetMovieImagesAsync(parsed.Id, language, context.RequestAborted),
                "show" => await tv.GetShowImagesAsync(parsed.Id, language, context.RequestAborted),
                "season" when parsed.Indices.Length == 1 => await tv.GetSeasonImagesAsync(
                    parsed.Id, parsed.Indices[0], language, context.RequestAborted),
                "episode" when parsed.Indices.Length == 2 => await tv.GetEpisodeImagesAsync(
                    parsed.Id, parsed.Indices[0], parsed.Indices[1], language, context.RequestAborted),
                _ => null
            };
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

    /// <summary>Only tmdb-sourced keys are resolvable; everything else is unknown here.</summary>
    private static bool TryParseTmdbKey(string ratingKey, out ParsedRatingKey parsed)
    {
        parsed = default!;
        return RatingKey.TryParse(ratingKey, out parsed) && parsed.Source == "tmdb";
    }
}
