using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Metacache.Core.Cache;

public static class CacheServiceCollectionExtensions
{
    /// <summary>
    /// Registers the cache stack (SQLite store, image store, upstream gateway, item cache)
    /// against the given options. All services are process-lifetime singletons — the store
    /// holds one connection (WAL) and the shared HttpClient gets connection pooling.
    /// </summary>
    public static IServiceCollection AddMetacacheCache(this IServiceCollection services, CacheOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);

        services.AddSingleton(options); // resolvable by /metrics for disk usage
        services.AddSingleton<IClock>(SystemClock.Instance);
        services.AddSingleton<SingleFlight>();
        services.AddSingleton<UpstreamMetrics>();
        services.AddSingleton<ScrapeHistory>();
        services.AddSingleton(_ => new CacheStore(options.DataSource));
        services.AddSingleton<IUpstreamHttp>(_ =>
            new HttpUpstreamClient(new HttpClient { Timeout = TimeSpan.FromSeconds(30) }));
        services.AddSingleton(_ => new ImageStore(options.ImageDirectory, options.MaxImageBytes));
        services.AddSingleton<UpstreamCache>();
        services.AddSingleton<MetadataCache>();
        services.AddSingleton(sp => new ImageCache(
            sp.GetRequiredService<CacheStore>(),
            sp.GetRequiredService<ImageStore>(),
            sp.GetRequiredService<IUpstreamHttp>(),
            sp.GetRequiredService<SingleFlight>(),
            sp.GetRequiredService<IClock>(),
            sp.GetRequiredService<UpstreamMetrics>(),
            sp.GetRequiredService<ILogger<ImageCache>>(),
            options.MaxImageTotalBytes));
        return services;
    }
}
