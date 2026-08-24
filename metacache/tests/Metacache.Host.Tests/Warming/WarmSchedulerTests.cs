using Metacache.Plex.Warming;

namespace Metacache.Host.Tests.Warming;

public class WarmSchedulerTests
{
    private static readonly DateTimeOffset Noon = new(2026, 8, 24, 12, 0, 0, TimeSpan.Zero);

    [Fact]
    public void Schedule_in_the_future_runs_today()
    {
        DateTimeOffset next = WarmScheduler.NextRunTime("18:00", Noon);
        Assert.Equal(new DateTimeOffset(2026, 8, 24, 18, 0, 0, TimeSpan.Zero), next);
    }

    [Fact]
    public void Schedule_already_passed_runs_tomorrow()
    {
        DateTimeOffset next = WarmScheduler.NextRunTime("06:30", Noon);
        Assert.Equal(new DateTimeOffset(2026, 8, 25, 6, 30, 0, TimeSpan.Zero), next);
    }

    [Fact]
    public void Exact_schedule_time_runs_now()
    {
        DateTimeOffset next = WarmScheduler.NextRunTime("12:00", Noon);
        Assert.Equal(Noon, next);
    }

    [Fact]
    public void Midnight_schedule_rolls_over_cleanly()
    {
        DateTimeOffset next = WarmScheduler.NextRunTime("00:00", Noon);
        Assert.Equal(new DateTimeOffset(2026, 8, 25, 0, 0, 0, TimeSpan.Zero), next);
    }

    [Fact]
    public void Seconds_are_supported()
    {
        DateTimeOffset next = WarmScheduler.NextRunTime("23:59:30", Noon);
        Assert.Equal(new DateTimeOffset(2026, 8, 24, 23, 59, 30, TimeSpan.Zero), next);
    }

    [Fact]
    public void Invalid_schedule_throws()
    {
        Assert.Throws<ArgumentException>(() => WarmScheduler.NextRunTime("25:00", Noon));
        Assert.Throws<ArgumentException>(() => WarmScheduler.NextRunTime("", Noon));
    }
}
