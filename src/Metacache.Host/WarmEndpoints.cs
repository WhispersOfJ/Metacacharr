using System.Text.Json;
using Metacache.Plex.Warming;

namespace Metacache.Host;

/// <summary>
/// M3 warm-up surface (DESIGN.md §8): triggers the cache warmer against Radarr and
/// Sonarr. POST /warm/movies, /warm/shows, /warm/all — each returns the run summary,
/// or 409 when a warm is already in flight. GET /warm/status shows the live state.
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
    }

    private static async Task<IResult> Run(CacheWarmer warmer, Func<Task<Metacache.Core.Providers.WarmResult?>> run)
    {
        var result = await run().ConfigureAwait(false);
        return result is null
            ? Results.Json(new { error = "A warm is already running." }, JsonOptions, statusCode: StatusCodes.Status409Conflict)
            : Results.Json(result, JsonOptions);
    }
}
