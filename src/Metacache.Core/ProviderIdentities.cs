namespace Metacache.Core;

/// <summary>
/// Identity constants for the Metacache Plex metadata providers.
/// Plex requires custom provider identifiers to start with "tv.plex.agents.custom."
/// and the suffix may only contain ASCII letters, digits and periods.
/// </summary>
public static class ProviderIdentities
{
    public const string Version = "1.0.0";

    public const string Movie = "tv.plex.agents.custom.metacache.movie";
    public const string Tv = "tv.plex.agents.custom.metacache.tv";
}
