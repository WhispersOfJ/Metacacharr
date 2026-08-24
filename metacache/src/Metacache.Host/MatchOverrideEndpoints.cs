using System.Globalization;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Plex;

namespace Metacache.Host;

/// <summary>
/// Admin surface for the manual-match-pin feature (DESIGN.md §15.10): CRUD over the
/// persisted match overrides and a review/pin loop over captured auto-match failures.
/// The match endpoints consult these before any upstream search, so a pin here is the
/// authoritative answer for that hint.
/// </summary>
public static class MatchOverrideEndpoints
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public static void MapMatchOverrideEndpoints(this WebApplication app)
    {
        app.MapGet("/admin/overrides", (CacheStore store) => Results.Json(store.ListOverrides(), Json));
        app.MapPost("/admin/overrides", (HttpContext context, CacheStore store, IClock clock) =>
            CreateOverrideAsync(context, store, clock));
        app.MapDelete("/admin/overrides/{key}", (string key, CacheStore store) =>
            store.DeleteOverride(key) ? Results.NoContent() : Results.NotFound());

        app.MapGet("/admin/unmatched", (CacheStore store) => Results.Json(store.ListUnmatched(), Json));
        app.MapPost("/admin/unmatched/{key}/pin", (string key, HttpContext context, CacheStore store, IClock clock) =>
            PinAsync(key, context, store, clock));
        app.MapDelete("/admin/unmatched/{key}", (string key, CacheStore store) =>
            store.DeleteUnmatched(key) ? Results.NoContent() : Results.NotFound());
        app.MapDelete("/admin/unmatched", (CacheStore store) =>
            Results.Json(new { removed = store.ClearUnmatched() }, Json));
    }

    private sealed record CreateOverrideRequest(string? Key, string? Kind, string? Target, string? Notes);

    private static async Task<IResult> CreateOverrideAsync(
        HttpContext context, CacheStore store, IClock clock)
    {
        CreateOverrideRequest? body;
        try
        {
            body = await context.Request.ReadFromJsonAsync<CreateOverrideRequest>(Json, context.RequestAborted);
        }
        catch (JsonException)
        {
            return Results.Json(new { error = "Request body is not valid JSON." }, statusCode: StatusCodes.Status400BadRequest);
        }

        if (body is null || string.IsNullOrWhiteSpace(body.Key) || string.IsNullOrWhiteSpace(body.Target))
            return Results.Json(new { error = "'key' and 'target' are required." }, statusCode: StatusCodes.Status400BadRequest);

        string key = body.Key.Trim();
        string kind = (body.Kind ?? "").Trim().ToLowerInvariant();
        if (kind is not ("movie" or "show" or "season" or "episode"))
            return Results.Json(new { error = "'kind' must be one of movie, show, season, episode." }, statusCode: StatusCodes.Status400BadRequest);

        if (!RatingKey.TryParse(body.Target, out ParsedRatingKey parsed) || parsed.Source != "tmdb")
            return Results.Json(new { error = "'target' must be a tmdb-source rating key, e.g. tmdb-movie-105 or tmdb-episode-15260-1-1." },
                statusCode: StatusCodes.Status400BadRequest);
        if (parsed.Kind != kind)
            return Results.Json(new { error = $"'kind' ({kind}) does not match the target's kind ({parsed.Kind})." },
                statusCode: StatusCodes.Status400BadRequest);

        store.PutOverride(new MatchOverride(
            key, kind, body.Target.Trim(), string.IsNullOrWhiteSpace(body.Notes) ? null : body.Notes.Trim(),
            clock.UtcNow.ToString("O", CultureInfo.InvariantCulture)));
        return Results.Json(store.GetOverride(key), Json);
    }

    private sealed record PinRequest(string? Target, string? Notes);

    /// <summary>Pins a match for an unmatched entry: creates the override from the entry's key/kind, then drops the entry.</summary>
    private static async Task<IResult> PinAsync(string key, HttpContext context, CacheStore store, IClock clock)
    {
        UnmatchedEntry? entry = store.ListUnmatched().FirstOrDefault(e => e.Key == key);
        if (entry is null)
            return Results.NotFound();

        PinRequest? body;
        try
        {
            body = await context.Request.ReadFromJsonAsync<PinRequest>(Json, context.RequestAborted);
        }
        catch (JsonException)
        {
            return Results.Json(new { error = "Request body is not valid JSON." }, statusCode: StatusCodes.Status400BadRequest);
        }

        if (body is null || string.IsNullOrWhiteSpace(body.Target))
            return Results.Json(new { error = "'target' is required." }, statusCode: StatusCodes.Status400BadRequest);

        if (!RatingKey.TryParse(body.Target, out ParsedRatingKey parsed) || parsed.Source != "tmdb")
            return Results.Json(new { error = "'target' must be a tmdb-source rating key, e.g. tmdb-movie-105." },
                statusCode: StatusCodes.Status400BadRequest);

        store.PutOverride(new MatchOverride(
            entry.Key, entry.Kind, body.Target.Trim(), string.IsNullOrWhiteSpace(body.Notes) ? null : body.Notes.Trim(),
            clock.UtcNow.ToString("O", CultureInfo.InvariantCulture)));
        store.DeleteUnmatched(key);
        return Results.Json(store.GetOverride(key), Json);
    }
}
