namespace Metacache.Core.Cache;

/// <summary>One /metrics/prometheus scrape observation (the counters at scrape time).</summary>
public sealed record ScrapePoint(long UnixSeconds, double HitRate, long Hits, long Requests);

/// <summary>
/// In-process ring buffer of the last N <c>/metrics/prometheus</c> scrape snapshots,
/// so the dashboard can overlay what Prometheus sees against its own 3 s polling.
/// The server keeps the history (not the browser): it survives page reloads and
/// matches the actual scrape rate however the Prometheus scrape interval is set.
/// </summary>
public sealed class ScrapeHistory
{
    private readonly int _capacity;
    private readonly object _gate = new();
    private readonly Queue<ScrapePoint> _points;

    public ScrapeHistory(int capacity = 120)
    {
        _capacity = capacity;
        _points = new Queue<ScrapePoint>(capacity);
    }

    public void Record(ScrapePoint point)
    {
        lock (_gate)
        {
            if (_points.Count == _capacity)
                _points.Dequeue();
            _points.Enqueue(point);
        }
    }

    /// <summary>Oldest→newest copy of the recorded points.</summary>
    public IReadOnlyList<ScrapePoint> Snapshot()
    {
        lock (_gate)
        {
            return _points.ToArray();
        }
    }
}
