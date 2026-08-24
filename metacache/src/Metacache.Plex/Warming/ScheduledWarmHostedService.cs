using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Metacache.Plex.Warming;

/// <summary>
/// M3 scheduled warm (DESIGN.md §8): runs <see cref="CacheWarmer.WarmAllAsync"/> once
/// per day at the configured wall-clock time. Uses a <see cref="TimeProvider"/> so
/// tests can drive the clock; a blank-URL warm is a cheap no-op (skipped).
/// </summary>
public sealed class ScheduledWarmHostedService : BackgroundService
{
    private readonly CacheWarmer _warmer;
    private readonly WarmOptions _options;
    private readonly TimeProvider _time;
    private readonly ILogger<ScheduledWarmHostedService> _logger;

    public ScheduledWarmHostedService(
        CacheWarmer warmer, WarmOptions options, TimeProvider time, ILogger<ScheduledWarmHostedService> logger)
    {
        _warmer = warmer;
        _options = options;
        _time = time;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_options.Enabled)
        {
            _logger.LogInformation("Scheduled cache warming is disabled");
            return;
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            DateTimeOffset now = _time.GetUtcNow();
            DateTimeOffset next = WarmScheduler.NextRunTime(_options.ScheduleTime, now);
            _logger.LogInformation("Next cache warm scheduled for {Next:O} (local {Local})", next, next.LocalDateTime);
            try
            {
                await Task.Delay(next - now, _time, stoppingToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }

            try
            {
                var result = await _warmer.WarmAllAsync(stoppingToken).ConfigureAwait(false);
                _logger.LogInformation(
                    "Scheduled warm finished: {Items} items, {Images} images, {Missing} missing, {Errors} errors",
                    result?.ItemsWarmed ?? -1, result?.ImagesWarmed ?? -1, result?.Missing ?? -1, result?.Errors ?? -1);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                _logger.LogError(ex, "Scheduled cache warm failed");
            }
        }
    }
}
