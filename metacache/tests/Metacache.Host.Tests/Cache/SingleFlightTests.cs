using Metacache.Core.Cache;

namespace Metacache.Host.Tests.Cache;

public class SingleFlightTests
{
    [Fact]
    public async Task Concurrent_callers_share_one_execution()
    {
        var flight = new SingleFlight();
        int calls = 0;

        Task<string>[] tasks = Enumerable.Range(0, 10)
            .Select(_ => flight.RunAsync("key", async () =>
            {
                Interlocked.Increment(ref calls);
                await Task.Delay(20);
                return "value";
            }))
            .ToArray();

        string[] results = await Task.WhenAll(tasks);

        Assert.All(results, r => Assert.Equal("value", r));
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task Failed_call_does_not_poison_future_calls()
    {
        var flight = new SingleFlight();
        int calls = 0;

        Task<string> Call() => flight.RunAsync("key", () =>
        {
            calls++;
            return calls == 1
                ? Task.FromException<string>(new InvalidOperationException("boom"))
                : Task.FromResult("ok");
        });

        await Assert.ThrowsAsync<InvalidOperationException>(Call);
        Assert.Equal("ok", await Call());
        Assert.Equal(2, calls);
    }

    [Fact]
    public async Task Different_keys_execute_independently()
    {
        var flight = new SingleFlight();

        var first = await flight.RunAsync("a", () => Task.FromResult(1));
        var second = await flight.RunAsync("b", () => Task.FromResult(2));

        Assert.Equal(1, first);
        Assert.Equal(2, second);
    }
}
