namespace Metacache.Core.Cache;

/// <summary>Maps artwork URLs to content types for serving cached images.</summary>
public static class ImageContentTypes
{
    private static readonly Dictionary<string, string> Map = new(StringComparer.OrdinalIgnoreCase)
    {
        ["jpg"] = "image/jpeg",
        ["jpeg"] = "image/jpeg",
        ["png"] = "image/png",
        ["webp"] = "image/webp",
        ["gif"] = "image/gif",
        ["avif"] = "image/avif",
        ["svg"] = "image/svg+xml"
    };

    public static string FromUrl(string url)
    {
        try
        {
            string extension = Path.GetExtension(new Uri(url).AbsolutePath).TrimStart('.');
            return extension.Length > 0 && Map.TryGetValue(extension, out string? contentType)
                ? contentType
                : "application/octet-stream";
        }
        catch (UriFormatException)
        {
            return "application/octet-stream";
        }
    }
}
