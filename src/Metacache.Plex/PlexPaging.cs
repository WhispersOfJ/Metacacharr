using Microsoft.AspNetCore.Http;

namespace Metacache.Plex;

/// <summary>
/// Plex container paging (docs/API Endpoints.md): X-Plex-Container-Size (default 20)
/// and X-Plex-Container-Start (default 1, 1-based) may arrive as headers or query
/// params. Applies to /children and /grandchildren responses: MediaContainer `size`
/// is the page length, `totalSize` the full list, `offset` the 0-based start.
/// </summary>
internal static class PlexPaging
{
    public const int DefaultPageSize = 20;

    public static (IReadOnlyList<T> Page, int TotalSize, int Offset) Page<T>(HttpRequest request, IReadOnlyList<T> all)
    {
        int pageSize = Math.Clamp(GetInt(request, "X-Plex-Container-Size", DefaultPageSize), 1, 1000);
        int start = Math.Max(GetInt(request, "X-Plex-Container-Start", 1), 1);
        int offset = start - 1;

        var page = all.Skip(offset).Take(pageSize).ToList();
        return (page, all.Count, offset);
    }

    private static int GetInt(HttpRequest request, string name, int fallback)
    {
        string? raw = null;
        if (request.Headers.TryGetValue(name, out var header) && !string.IsNullOrEmpty(header))
        {
            raw = header.ToString();
        }
        else
        {
            foreach (var (key, value) in request.Query)
            {
                if (string.Equals(key, name, StringComparison.OrdinalIgnoreCase) && !string.IsNullOrEmpty(value))
                {
                    raw = value.ToString();
                    break;
                }
            }
        }

        return int.TryParse(raw, out int parsed) ? parsed : fallback;
    }
}
