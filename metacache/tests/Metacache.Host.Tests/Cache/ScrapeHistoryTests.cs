using Metacache.Core.Cache;

namespace Metacache.Host.Tests.Cache;

public class ScrapeHistoryTests
{
    [Fact]
    public void Keeps_only_the_most_recent_capacity_points()
    {
        var history = new ScrapeHistory(capacity: 3);
        for (int i = 1; i <= 5; i++)
            history.Record(new ScrapePoint(i, i / 10.0, i, i));

        IReadOnlyList<ScrapePoint> points = history.Snapshot();

        Assert.Equal(3, points.Count);
        Assert.Equal(3, points[0].UnixSeconds);
        Assert.Equal(5, points[^1].UnixSeconds);
        Assert.Equal(new double[] { 0.3, 0.4, 0.5 }, points.Select(p => p.HitRate));
    }

    [Fact]
    public void Snapshot_is_ordered_oldest_to_newest()
    {
        var history = new ScrapeHistory();
        history.Record(new ScrapePoint(100, 0.1, 1, 1));
        history.Record(new ScrapePoint(200, 0.5, 2, 3));

        IReadOnlyList<ScrapePoint> points = history.Snapshot();

        Assert.Equal(new long[] { 100, 200 }, points.Select(p => p.UnixSeconds));
        Assert.Equal(new long[] { 1, 2 }, points.Select(p => p.Hits));
        Assert.Equal(new long[] { 1, 3 }, points.Select(p => p.Requests));
    }

    [Fact]
    public void Snapshot_isolates_from_later_records()
    {
        var history = new ScrapeHistory();
        history.Record(new ScrapePoint(1, 0.2, 1, 1));

        IReadOnlyList<ScrapePoint> first = history.Snapshot();
        history.Record(new ScrapePoint(2, 0.9, 2, 2));

        Assert.Single(first);
        Assert.Equal(2, history.Snapshot().Count);
    }
}
