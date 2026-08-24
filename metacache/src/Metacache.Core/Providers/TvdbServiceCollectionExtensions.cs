using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Core.Providers;

public static class TvdbServiceCollectionExtensions
{
    /// <summary>
    /// Registers the TVDB v4 client. Requires the cache stack (AddMetacacheCache) to be
    /// registered first — data calls route through UpstreamCache. A blank ApiKey is
    /// allowed at registration time; calls throw <see cref="TvdbConfigurationException"/>
    /// until a key is configured (same lazy behavior as the TMDB client).
    /// </summary>
    public static IServiceCollection AddTvdbClient(this IServiceCollection services, TvdbOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddSingleton(options);
        services.AddSingleton<TvdbClient>();
        return services;
    }
}
