using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Core.Cache;

public static class CacheServiceCollectionExtensions
{
    /// <summary>
    /// Registers the cache stack against a single SQLite database file. The store is a
    /// process-lifetime singleton (single connection, WAL). The shared HttpClient gets
    /// connection pooling automatically and is never disposed until shutdown.
    /// </summary>
    public static IServiceCollection AddMetacacheCache(this IServiceCollection services, string dataSource)
    {
        services.AddSingleton<IClock>(SystemClock.Instance);
        services.AddSingleton<SingleFlight>();
        services.AddSingleton(_ => new CacheStore(dataSource));
        services.AddSingleton<IUpstreamHttp>(_ =>
            new HttpUpstreamClient(new HttpClient { Timeout = TimeSpan.FromSeconds(30) }));
        services.AddSingleton<UpstreamCache>();
        services.AddSingleton<MetadataCache>();
        return services;
    }
}
