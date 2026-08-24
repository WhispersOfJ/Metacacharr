using System.Text.Json;
using Metacache.Plex.Warming;

namespace Metacache.Host;

/// <summary>
/// M3 warm-up surface (DESIGN.md §8): triggers the cache warmer against Radarr and
/// Sonarr. POST /warm/movies, /warm/shows, /warm/all — each returns the run summary,
/// or 409 when a warm is already in flight. GET /warm/status shows the live state.
/// The /webhook/radarr and /webhook/sonarr endpoints warm a single item on new
/// imports (event-driven, §8), answering the ARR apps' webhook test button too.
/// </summary>
public static class WarmEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static void MapWarmEndpoints(this WebApplication app)
    {
        app.MapGet("/warm/status", (CacheWarmer warmer) => Results.Json(warmer.Status, JsonOptions));
        app.MapPost("/warm/movies", (CacheWarmer warmer, CancellationToken ct) => Run(warmer, () => warmer.WarmMoviesAsync(ct)));
        app.MapPost("/warm/shows", (CacheWarmer warmer, CancellationToken ct) => Run(warmer, () => warmer.WarmShowsAsync(ct)));
        app.MapPost("/warm/all", (CacheWarmer warmer, CancellationToken ct) => Run(warmer, () => warmer.WarmAllAsync(ct)));
        app.MapPost("/webhook/radarr", (CacheWarmer warmer, HttpContext context, CancellationToken ct) =>
            HandleArrWebhookAsync(warmer, context, ct, "movie", "tmdbId"));
        app.MapPost("/webhook/sonarr", (CacheWarmer warmer, HttpContext context, CancellationToken ct) =>
            HandleArrWebhookAsync(warmer, context, ct, "series", "tvdbId"));
    }

    /// <summary>Warms the single item named by an ARR webhook payload (eventType Test → ok).</summary>
    private static async Task<IResult> HandleArrWebhookAsync(
        CacheWarmer warmer, HttpContext context, CancellationToken ct, string itemProperty, string idProperty)
    {
        string body = await new StreamReader(context.Request.Body).ReadToEndAsync(ct).ConfigureAwait(false);
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(body);
        }
        catch (JsonException)
        {
            return Results.Json(new { error = "Request body is not valid JSON." }, JsonOptions, statusCode: StatusCodes.Status400BadRequest);
        }

        using (doc)
        {
            string eventType = doc.RootElement.TryGetProperty("eventType", out JsonElement eventElement)
                ? eventElement.GetString() ?? string.Empty
                : string.Empty;
            if (string.Equals(eventType, "Test", StringComparison.OrdinalIgnoreCase))
                return Results.Json(new { result = "ok" }, JsonOptions);

            if (!doc.RootElement.TryGetProperty(itemProperty, out JsonElement item)
                || !item.TryGetProperty(idProperty, out JsonElement idElement)
                || idElement.ValueKind != JsonValueKind.Number
                || !idElement.TryGetInt32(out int id))
                return Results.Json(new { result = "ignored" }, JsonOptions);

            var result = idProperty == "tmdbId"
                ? await warmer.WarmMovieAsync(id, ct).ConfigureAwait(false)
                : await warmer.WarmShowByTvdbAsync(id, ct).ConfigureAwait(false);
            return result is null
                ? Results.Json(new { error = "A warm is already running." }, JsonOptions, statusCode: StatusCodes.Status409Conflict)
                : Results.Json(result, JsonOptions);
        }
    }

    private static async Task<IResult> Run(CacheWarmer warmer, Func<Task<Metacache.Core.Providers.WarmResult?>> run)
    {
        var result = await run().ConfigureAwait(false);
        return result is null
            ? Results.Json(new { error = "A warm is already running." }, JsonOptions, statusCode: StatusCodes.Status409Conflict)
            : Results.Json(result, JsonOptions);
    }
}
