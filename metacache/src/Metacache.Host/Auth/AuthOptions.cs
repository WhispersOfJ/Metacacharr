namespace Metacache.Host.Auth;

/// <summary>
/// Configuration for bearer-token authentication on protected endpoints.
/// When <see cref="ApiKey"/> is empty or null, authentication is disabled entirely
/// (backward compatible with unauthenticated deployments).
/// </summary>
public sealed record AuthOptions(string? ApiKey = null)
{
    public static AuthOptions FromConfig(IConfigurationSection section) => new(
        ApiKey: section["ApiKey"] ?? null);
}
