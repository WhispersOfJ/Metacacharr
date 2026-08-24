namespace Metacache.Core.Providers;

/// <summary>A movie in Radarr's library (GET /api/v3/movie).</summary>
public sealed record ArrMovie(
    int Id,
    string? Title,
    int? TmdbId,
    int? Year);

/// <summary>A series in Sonarr's library (GET /api/v3/series).</summary>
public sealed record ArrSeries(
    int Id,
    string? Title,
    int? TvdbId,
    int? Year);

/// <summary>Outcome of one warm run against one ARR source.</summary>
public sealed record WarmResult(
    string Source,
    int ItemsWarmed,
    int ImagesWarmed,
    int Missing,
    int Errors,
    bool Skipped,
    double ElapsedSeconds)
{
    public static WarmResult SkippedRun(string source) =>
        new(source, 0, 0, 0, 0, Skipped: true, 0);
}

/// <summary>Live snapshot of the warmer (for GET /warm/status).</summary>
/// <summary>
/// Live warmer state. <see cref="CompletedAt"/> is when the most recent warm
/// attempt finished (success or failure) — the /metrics/prometheus staleness
/// alert keys off it, so a failed warm still refreshes the timestamp.
/// </summary>
public sealed record WarmStatus(bool IsRunning, WarmResult? LastResult, DateTimeOffset? CompletedAt = null);

/// <summary>Live progress snapshot during a warm run (for /warm/progress).</summary>
public sealed record WarmProgress(
    string Source,
    int TotalItems,
    int ProcessedItems,
    int ImagesWarmed,
    int Errors,
    string? CurrentItem,
    DateTimeOffset StartedAt)
{
    public double ElapsedSeconds => (DateTimeOffset.UtcNow - StartedAt).TotalSeconds;
    public double? EstimatedTotalSeconds => ProcessedItems > 0 ? ElapsedSeconds / ProcessedItems * TotalItems : null;
    public double? EstimatedRemainingSeconds => EstimatedTotalSeconds.HasValue ? Math.Max(0, EstimatedTotalSeconds.Value - ElapsedSeconds) : null;
    public double PercentComplete => TotalItems > 0 ? (double)ProcessedItems / TotalItems * 100 : 0;
}
