namespace Metacache.Core.Providers;

/// <summary>Configuration for the TVDB v4 provider (DESIGN.md §15.9).</summary>
public sealed record TvdbOptions(
    string ApiKey,
    string BaseUrl = "https://api4.thetvdb.com");
