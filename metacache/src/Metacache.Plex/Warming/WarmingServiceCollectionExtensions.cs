using Metacache.Core.Providers;
using Metacache.Plex.Warming;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Metacache.Plex;

public static class WarmingServiceCollectionExtensions
{
    /// <summary>
    /// Registers the M3 cache warmer (DESIGN.md §8) and, when <paramref name="warm"/>
    /// is supplied, the scheduled nightly warm. Requires the cache stack, TMDB client,
    /// and provider services to already be registered.
    /// </summary>
    public static IServiceCollection AddMetacacheWarming(this IServiceCollection services, ArrOptions arr, WarmOptions? warm = null)
    {
        ArgumentNullException.ThrowIfNull(arr);
        services.AddSingleton(arr);
        services.AddSingleton(warm ?? new WarmOptions());
        services.AddSingleton<CacheWarmer>();

        if (warm is not null)
        {
            services.AddSingleton(TimeProvider.System);
            services.AddHostedService<ScheduledWarmHostedService>();
        }
        return services;
    }
}
