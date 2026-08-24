using Metacache.Core.Providers;
using Metacache.Plex.Warming;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Plex;

public static class WarmingServiceCollectionExtensions
{
    /// <summary>
    /// Registers the M3 cache warmer (DESIGN.md §8). Requires the cache stack,
    /// TMDB client, and provider services to already be registered.
    /// </summary>
    public static IServiceCollection AddMetacacheWarming(this IServiceCollection services, ArrOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddSingleton(options);
        services.AddSingleton<CacheWarmer>();
        return services;
    }
}
