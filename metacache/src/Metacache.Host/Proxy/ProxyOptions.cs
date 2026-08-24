namespace Metacache.Host.Proxy;

/// <summary>
/// Configuration for the ARR proxy face (DESIGN.md §10). The proxy runs on a second
/// port (default 443) as an HTTPS reverse proxy for upstream metadata APIs, making
/// Radarr/Sonarr hit the local cache transparently via DNS override.
/// </summary>
public sealed record ProxyOptions(
    bool Enabled = false,
    int HttpPort = 443,
    string CertDirectory = "data/certs",
    string? BindAddress = null)
{
    /// <summary>Build from the Metacache:Proxy config section.</summary>
    public static ProxyOptions FromConfig(IConfigurationSection section) => new(
        Enabled: section.GetValue<bool?>("Enabled") ?? false,
        HttpPort: section.GetValue<int?>("HttpPort") ?? 443,
        CertDirectory: section["CertDirectory"] ?? "data/certs",
        BindAddress: section["BindAddress"]);
}
