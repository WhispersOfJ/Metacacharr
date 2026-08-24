using Metacache.Core.Cache;

namespace Metacache.Host.Tests.Cache;

public sealed class FakeClock : IClock
{
    public FakeClock(DateTimeOffset utcNow) => UtcNow = utcNow;

    public DateTimeOffset UtcNow { get; set; }
}

public sealed class FakeUpstream : IUpstreamHttp
{
    /// <summary>Per-request handler; throw to simulate transport failures.</summary>
    public Func<UpstreamRequest, UpstreamResponse> Handler { get; set; } =
        _ => throw new InvalidOperationException("No upstream handler configured");

    public List<UpstreamRequest> Requests { get; } = [];

    public Task<UpstreamResponse> SendAsync(UpstreamRequest request, CancellationToken cancellationToken)
    {
        Requests.Add(request);
        return Task.FromResult(Handler(request));
    }
}

public static class TestBytes
{
    public static byte[] Of(string text) => System.Text.Encoding.UTF8.GetBytes(text);

    public static string Read(byte[] body) => System.Text.Encoding.UTF8.GetString(body);
}
