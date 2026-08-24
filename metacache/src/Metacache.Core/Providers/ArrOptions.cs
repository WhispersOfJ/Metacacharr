namespace Metacache.Core.Providers;

/// <summary>
/// M3 cache-warming config (DESIGN.md §8): where the ARR apps live and how many
/// items to warm in parallel. A blank URL disables that source.
/// </summary>
public sealed record ArrOptions(
    string RadarrUrl = "",
    string RadarrApiKey = "",
    string SonarrUrl = "",
    string SonarrApiKey = "",
    int Concurrency = 4);
