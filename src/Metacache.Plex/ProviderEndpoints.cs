using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Metacache.Plex.Models;

namespace Metacache.Plex;

/// <summary>
/// Maps the Plex metadata-provider HTTP surface. M0 serves the provider
/// definitions only; match/metadata endpoints land in M1 (DESIGN.md §12).
/// </summary>
public static class ProviderEndpoints
{
    public static void MapProviderEndpoints(this WebApplication app)
    {
        app.MapGet("/", () => Results.Text(
            "Metacache metadata provider. Provider definitions: GET /movie, GET /tv. Health: GET /healthz.",
            "text/plain"));

        app.MapGet("/movie", () => Results.Json(ProviderCatalog.Movie));
        app.MapGet("/tv", () => Results.Json(ProviderCatalog.Tv));
    }
}
