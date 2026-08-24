namespace Metacache.Host.Proxy;

/// <summary>
/// Maps incoming SNI hostnames (e.g. <c>api.themoviedb.org</c>) to the upstream base
/// URLs they should be forwarded to. DNS override makes ARR apps send requests here;
/// the router reconstructs the original upstream URL from the SNI hostname + original
/// path + query so the upstream cache sees the same key it would for a direct call.
/// </summary>
public sealed class ProxyRouter
{
    private readonly IReadOnlyDictionary<string, string> _routes;

    public ProxyRouter(IReadOnlyDictionary<string, string> routes)
    {
        _routes = routes;
    }

    /// <summary>
    /// Returns the upstream base URL for the given SNI hostname, or null if the
    /// hostname is not in the route table (the proxy should 404/421).
    /// </summary>
    public string? Resolve(string sniHostname)
    {
        if (string.IsNullOrEmpty(sniHostname))
            return null;
        return _routes.TryGetValue(sniHostname, out string? upstream) ? upstream : null;
    }

    /// <summary>
    /// Reconstructs the full upstream URL from the SNI hostname, the original request
    /// path + query, and the route table. The result is what the upstream cache would
    /// see for a direct call — the cache key is identical.
    /// </summary>
    public string ReconstructUrl(string sniHostname, PathString path, QueryString query)
    {
        string? upstream = Resolve(sniHostname);
        if (upstream is null)
            throw new InvalidOperationException($"No route for hostname '{sniHostname}'.");

        // upstream is a base like "https://api.themoviedb.org/3" — strip trailing slash
        // so path segments concatenate cleanly.
        string baseUrl = upstream.TrimEnd('/');
        string fullPath = path.HasValue ? path.Value! : "/";
        string qs = query.HasValue ? query.Value! : "";
        return $"{baseUrl}{fullPath}{qs}";
    }

    /// <summary>
    /// All hostnames in the route table.
    /// </summary>
    public IReadOnlyCollection<string> Hostnames => _routes.Keys.ToList().AsReadOnly();

    /// <summary>
    /// Creates the default route table from config. Each entry is a hostname→upstream
    /// base URL mapping.
    /// </summary>
    public static ProxyRouter FromConfig(IConfigurationSection section)
    {
        var routes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        // Defaults from DESIGN.md §10: the four ARR-facing upstream hosts
        string tmdbApi = section["TmdbApi"] ?? "https://api.themoviedb.org/3";
        string tmdbImage = section["TmdbImage"] ?? "https://image.tmdb.org/t/p/original";
        string tvdbApi = section["TvdbApi"] ?? "https://api4.thetvdb.com";
        string fanartApi = section["FanartApi"] ?? "https://webservice.fanart.tv/v3";

        routes["api.themoviedb.org"] = tmdbApi;
        routes["image.tmdb.org"] = tmdbImage;
        routes["api.thetvdb.com"] = tvdbApi;
        routes["webservice.fanart.tv"] = fanartApi;

        // Allow overrides/additions via config
        if (section.GetSection("Routes") is { } custom)
        {
            foreach (var child in custom.GetChildren())
            {
                if (!string.IsNullOrEmpty(child.Key) && !string.IsNullOrEmpty(child.Value))
                    routes[child.Key] = child.Value;
            }
        }

        return new ProxyRouter(routes);
    }
}
