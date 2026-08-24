using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Core.Providers;
using Metacache.Host.Tests.Cache;
using Metacache.Plex;
using Metacache.Plex.Warming;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Time.Testing;

namespace Metacache.Host.Tests.Warming;

public class ScheduledWarmHostedServiceTests : IDisposable
{
    private readonly FakeUpstream _upstream = new();
    private readonly FakeTimeProvider _time = new(new DateTimeOffset(2026, 8, 24, 2, 59, 30, TimeSpan.Zero));
    private readonly ServiceProvider _services;
    private readonly string _imageDir;

    public ScheduledWarmHostedServiceTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-sched-{Guid.NewGuid():N}");
        _services = new ServiceCollection()
            .AddMetacacheCache(new CacheOptions(":memory:", _imageDir, 20L * 1024 * 1024, 10L * 1024 * 1024 * 1024))
            .AddMetacacheMatching(new ConfigurationBuilder().Build())
            .AddTmdbClient(new TmdbOptions(ApiKey: "test-api-key", BaseUrl: TmdbTestData.BaseUrl, Auth: TmdbAuthMode.Bearer))
            .AddMetacachePlexProviders()
            .AddMetacacheWarming(new ArrOptions(), new WarmOptions(Enabled: true, ScheduleTime: "03:00"))
            .AddSingleton<IUpstreamHttp>(_upstream)
            .AddSingleton<TimeProvider>(_time) // overrides TimeProvider.System for the hosted service
            .AddLogging()
            .BuildServiceProvider();
        _upstream.Route(); // no ARR URLs → the scheduled warm is a skipped no-op
    }

    public void Dispose()
    {
        _services.Dispose();
        if (Directory.Exists(_imageDir))
            Directory.Delete(_imageDir, recursive: true);
    }

    private static async Task WaitUntilAsync(Func<bool> condition, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (!condition() && DateTime.UtcNow < deadline)
            await Task.Delay(20);
        Assert.True(condition(), "condition did not become true within the timeout");
    }

    private static ScheduledWarmHostedService NewService(ServiceProvider services, FakeTimeProvider time, bool enabled)
    {
        var warmer = services.GetRequiredService<CacheWarmer>();
        return new ScheduledWarmHostedService(
            warmer, new WarmOptions(Enabled: enabled, ScheduleTime: "03:00"), time, NullLogger<ScheduledWarmHostedService>.Instance);
    }

    [Fact]
    public async Task Warm_runs_when_the_scheduled_time_arrives()
    {
        var warmer = _services.GetRequiredService<CacheWarmer>();
        var service = NewService(_services, _time, enabled: true);
        using var cts = new CancellationTokenSource();

        await service.StartAsync(cts.Token);
        await Task.Delay(100); // let ExecuteAsync register its delay with the fake clock
        Assert.Null(warmer.Status.LastResult); // not yet 03:00

        _time.Advance(TimeSpan.FromMinutes(1)); // 03:00:30 → delay completes, warm runs
        await WaitUntilAsync(() => warmer.Status.LastResult is not null, TimeSpan.FromSeconds(5));

        Assert.False(warmer.Status.IsRunning);
        Assert.Equal("all", warmer.Status.LastResult!.Source);
        await service.StopAsync(cts.Token);
    }

    [Fact]
    public async Task Disabled_schedule_never_runs()
    {
        var warmer = _services.GetRequiredService<CacheWarmer>();
        var service = NewService(_services, _time, enabled: false);
        using var cts = new CancellationTokenSource();

        await service.StartAsync(cts.Token);
        _time.Advance(TimeSpan.FromHours(2));
        await Task.Delay(100);

        Assert.Null(warmer.Status.LastResult);
        await service.StopAsync(cts.Token);
    }
}
