using System.Globalization;
using Metacache.Core.Cache;

namespace Metacache.Host;

/// <summary>
/// Serves cached artwork to Plex clients: GET /img/{hash}. The hash is the sha256 of the
/// original upstream URL (produced by <see cref="ImageCache.RewriteToLocalPath"/>); a
/// stored entry is streamed from disk, and a known-but-missing file is refetched from
/// upstream so the endpoint is self-healing. Unknown hashes 404.
///
/// Sized variants (DESIGN.md §21): `?width={size}` (from <see cref="ImageSizes.Allowed"/>, a
/// longest-side bound) serves a locally-resized JPEG variant, cached on disk — browse
/// lists ask for small thumbs and get them entirely from the local cache.
/// </summary>
public static class ImageEndpoints
{
    public static void MapImageEndpoints(this WebApplication app)
    {
        app.MapGet("/img/{hash}", async (string hash, ImageCache images, HttpContext context) =>
        {
            if (!ImageStore.IsValidHash(hash))
                return Results.NotFound();

            int? width = null;
            string? rawWidth = context.Request.Query["width"];
            if (!string.IsNullOrEmpty(rawWidth))
            {
                if (!int.TryParse(rawWidth, NumberStyles.None, CultureInfo.InvariantCulture, out int parsed)
                    || !ImageSizes.IsAllowed(parsed))
                    return Results.BadRequest(new { error = $"'width' must be one of {string.Join(", ", ImageSizes.Allowed)}." });
                width = parsed;
            }

            ImageResult? result;
            try
            {
                result = width is { } w
                    ? await images.GetVariantAsync(hash, w, context.RequestAborted)
                    : await images.GetByHashAsync(hash, context.RequestAborted);
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
