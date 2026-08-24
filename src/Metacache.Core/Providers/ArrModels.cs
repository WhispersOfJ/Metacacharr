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
public sealed record WarmStatus(bool IsRunning, WarmResult? LastResult);
