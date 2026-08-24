namespace Metacache.Plex.Warming;

/// <summary>
/// M3 scheduled-warming config (DESIGN.md §8 "Schedule: nightly incremental"):
/// whether the nightly warm is on and at what wall-clock time it runs.
/// </summary>
public sealed record WarmOptions(
    bool Enabled = true,
    string ScheduleTime = "03:00",
    IReadOnlyList<string>? Languages = null)
{
    /// <summary>Languages to warm for each item. Defaults to ["en-US"] if null/empty.</summary>
    public IReadOnlyList<string> EffectiveLanguages => Languages is { Count: > 0 } l ? l : ["en-US"];
}
