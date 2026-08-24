namespace Metacache.Plex.Warming;

/// <summary>
/// M3 scheduled-warming config (DESIGN.md §8 "Schedule: nightly incremental"):
/// whether the nightly warm is on and at what wall-clock time it runs.
/// </summary>
public sealed record WarmOptions(bool Enabled = true, string ScheduleTime = "03:00");
