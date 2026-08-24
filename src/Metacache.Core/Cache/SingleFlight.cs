using System.Collections.Concurrent;

namespace Metacache.Core.Cache;

/// <summary>
/// Keyed single-flight: concurrent callers for the same key share one execution, so a
/// thundering herd of identical requests results in a single upstream/database fetch.
///
/// The in-flight entry is keyed by the TaskCompletionSource's task and removed when the
/// shared work finishes — a failed run is therefore not sticky: the next caller starts
/// fresh work.
///
/// Cancellation note: the shared work runs with CancellationToken.None. A caller's own
/// cancellation does not abort a fetch other callers are waiting on — callers check their
/// token before launching and simply discard the result if they lose interest.
/// </summary>
public sealed class SingleFlight
{
    private readonly ConcurrentDictionary<string, Task<object?>> _inflight = new(StringComparer.Ordinal);

    public Task<T> RunAsync<T>(string key, Func<Task<T>> factory)
    {
        ArgumentException.ThrowIfNullOrEmpty(key);
        ArgumentNullException.ThrowIfNull(factory);

        while (true)
        {
            // Fast path: work for this key is already in flight (or finished) — share it.
            if (_inflight.TryGetValue(key, out Task<object?>? existing))
                return UnwrapAsync<T>(existing);

            // Claim the key. The task stored is the TCS's, which we remove when the work
            // completes — never reusing a finished result for a later caller.
            var tcs = new TaskCompletionSource<object?>(TaskCreationOptions.RunContinuationsAsynchronously);
            if (_inflight.TryAdd(key, tcs.Task))
            {
                _ = RunAndCompleteAsync(key, tcs, factory);
                return UnwrapAsync<T>(tcs.Task);
            }

            // Lost the race to claim the key; loop and take the winner's task.
        }
    }

    private async Task RunAndCompleteAsync<T>(string key, TaskCompletionSource<object?> tcs, Func<Task<T>> factory)
    {
        try
        {
            tcs.SetResult(await factory().ConfigureAwait(false));
        }
        catch (Exception ex)
        {
            tcs.SetException(ex);
        }
        finally
        {
            // Conditional remove so a newer entry for the same key is never clobbered.
            _inflight.TryRemove(new KeyValuePair<string, Task<object?>>(key, tcs.Task));
        }
    }

    private static async Task<T> UnwrapAsync<T>(Task<object?> task)
    {
        object? result = await task.ConfigureAwait(false);
        return (T)result!;
    }
}
