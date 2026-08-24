using Metacache.Core.Cache;

namespace Metacache.Host;

/// <summary>
/// Serves cached artwork to Plex clients: GET /img/{hash}. The hash is the sha256 of the
/// original upstream URL (produced by <see cref="ImageCache.RewriteToLocalPath"/>); a
/// stored entry is streamed from disk, and a known-but-missing file is refetched from
/// upstream so the endpoint is self-healing. Unknown hashes 404.
/// </summary>
public static class ImageEndpoints
{
    public static void MapImageEndpoints(this WebApplication app)
    {
        app.MapGet("/img/{hash}", async (string hash, ImageCache images, HttpContext context) =>
        {
            if (!ImageStore.IsValidHash(hash))
                return Results.NotFound();

            ImageResult? result;
            try
            {
                result = await images.GetByHashAsync(hash, context.RequestAborted);
            }
            catch (UpstreamException)
            {
                return Results.NotFound();
            }
            catch (ImageTooLargeException)
            {
                return Results.NotFound();
            }

            return result is null
                ? Results.NotFound()
                : Results.File(result.Path, result.ContentType, enableRangeProcessing: true);
        });
    }
}
