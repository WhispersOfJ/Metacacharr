namespace Metacache.Core.Cache;

/// <summary>
/// The normalized metadata store (DESIGN.md §7.1 layer 2). Items are keyed by
/// (id, language) and carry provider TTLs; fetches are single-flighted per (id, lang),
/// and a failed fetch falls back to the last good value (stale-if-error).
///
/// The fetcher is supplied by callers (M1: the TMDB/TVDB clients), which themselves
/// route raw HTTP through <see cref="UpstreamCache"/> for ETag revalidation.
/// </summary>
public sealed class MetadataCache
{
    private readonly CacheStore _store;
    private readonly SingleFlight _flight;
    private readonly IClock _clock;

    public MetadataCache(CacheStore store, SingleFlight flight, IClock clock)
    {
        _store = store;
        _flight = flight;
        _clock = clock;
    }

    /// <summary>Returns the item if it exists and is fresh, otherwise null.</summary>
    public CachedItem? GetFresh(string id, string lang, CachePolicy policy)
    {
        CachedItem? item = _store.GetItem(id, lang);
        if (item is null)
            return null;
        return item.ExpiresAt > _clock.UtcNow ? item : null;
    }

    public void Put(CachedItem item) => _store.PutItem(item);

    /// <summary>
    /// Returns a fresh item, fetching (and caching) it on miss or expiry. The shared
    /// fetch is not cancellable; caller cancellation only discards the result.
    /// </summary>
    public async Task<CachedItem> GetOrFetchAsync(
        ItemDescriptor descriptor,
        Func<CancellationToken, Task<ItemFetchResult>> fetcher,
        CachePolicy policy,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(descriptor);
        ArgumentNullException.ThrowIfNull(fetcher);
        cancellationToken.ThrowIfCancellationRequested();

        string flightKey = $"{descriptor.Id}|{descriptor.Lang}";
        Task<CachedItem> task = _flight.RunAsync(flightKey, () => FetchCoreAsync(descriptor, fetcher, policy));
        return await task.ConfigureAwait(false);
    }

    private async Task<CachedItem> FetchCoreAsync(
        ItemDescriptor descriptor, Func<CancellationToken, Task<ItemFetchResult>> fetcher, CachePolicy policy)
    {
        CachedItem? existing = _store.GetItem(descriptor.Id, descriptor.Lang);
        DateTimeOffset now = _clock.UtcNow;
        if (existing is not null && existing.ExpiresAt > now)
            return existing;

        try
        {
            ItemFetchResult result = await fetcher(CancellationToken.None).ConfigureAwait(false);
            var fresh = new CachedItem(
                descriptor.Id, descriptor.Kind, descriptor.Source, descriptor.SourceId, descriptor.Lang,
                result.Json, now, now + policy.Ttl, result.ETag);
            _store.PutItem(fresh);
            return fresh;
        }
        catch (Exception ex) when (existing is not null && ex is not OperationCanceledException)
        {
            // Stale-if-error for structured items: keep serving the last good value.
            return existing;
        }
    }
}
