using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Core.Providers;

public static class TmdbServiceCollectionExtensions
{
    /// <summary>
    /// Registers the TMDB client. Requires the cache stack (AddMetacacheCache) to be
    /// registered first — the client routes all traffic through UpstreamCache.
    /// </summary>
    public static IServiceCollection AddTmdbClient(this IServiceCollection services, TmdbOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddSingleton(options);
        services.AddSingleton<TmdbClient>();
        return services;
    }
}
