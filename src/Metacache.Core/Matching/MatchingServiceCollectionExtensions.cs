using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Core.Matching;

public static class MatchingServiceCollectionExtensions
{
    public const string ConfigurationSection = "Metacache:Matching";

    /// <summary>
    /// Binds <see cref="MatchPolicy"/> from the "Metacache:Matching" configuration section
    /// (environment-style overrides such as `Metacache__Matching__AutoMatchThreshold` work
    /// too) and registers it as a singleton, so matching weights and thresholds can be
    /// tuned without recompiling. Falls back to <see cref="MatchPolicy.Default"/> when the
    /// section is absent.
    /// </summary>
    public static IServiceCollection AddMetacacheMatching(this IServiceCollection services, IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);

        MatchPolicy policy = configuration.GetSection(ConfigurationSection).Get<MatchPolicy>() ?? MatchPolicy.Default;
        services.AddSingleton(policy);
        return services;
    }
}
