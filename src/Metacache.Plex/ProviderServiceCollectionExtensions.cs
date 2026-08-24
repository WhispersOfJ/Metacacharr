using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Plex;

public static class ProviderServiceCollectionExtensions
{
    /// <summary>
    /// Registers the provider services (movie match/metadata orchestration). Requires
    /// the cache stack (AddMetacacheCache) and TMDB client (AddTmdbClient) to be
    /// registered first.
    /// </summary>
    public static IServiceCollection AddMetacachePlexProviders(this IServiceCollection services)
    {
        services.AddSingleton<MovieProviderService>();
        return services;
    }
}
