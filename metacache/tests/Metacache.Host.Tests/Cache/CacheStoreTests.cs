using System.Globalization;
using Metacache.Core.Cache;
using Microsoft.Data.Sqlite;

namespace Metacache.Host.Tests.Cache;

public class CacheStoreTests
{
    private static readonly DateTimeOffset Now = DateTimeOffset.Parse("2026-08-24T00:00:00+00:00", CultureInfo.InvariantCulture);

    [Fact]
    public void Creates_the_three_cache_tables()
    {
        string dbPath = TempDbPath();
        try
        {
            using var _ = new CacheStore(dbPath, new FakeClock(Now)); // construction runs the schema

            List<string> tables;
            using (var conn = new SqliteConnection($"Data Source={dbPath}"))
            {
                conn.Open();
                using var cmd = conn.CreateCommand();
                cmd.CommandText = "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name;";
                using var reader = cmd.ExecuteReader();
                tables = [];
                while (reader.Read())
                    tables.Add(reader.GetString(0));
            }

            Assert.Contains("upstream_cache", tables);
            Assert.Contains("items", tables);
            Assert.Contains("urls", tables);
        }
        finally
        {
            File.Delete(dbPath);
            File.Delete(dbPath + "-wal");
            File.Delete(dbPath + "-shm");
        }
    }

    [Fact]
    public void Upstream_roundtrips_and_upsert_preserves_hits()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        var row = new CachedUpstreamRow("k1", "https://x/1", 200, "application/json", TestBytes.Of("v1"),
            Now, Now.AddHours(1), "w/\"e1\"", Now, Hits: 0);

        store.PutUpstream(row);
        CachedUpstreamRow? read = store.GetUpstream("k1");

        Assert.NotNull(read);
        // Records with byte[] fields don't compare by value; assert field-by-field.
        Assert.Equal(row.Key, read.Key);
        Assert.Equal(row.Url, read.Url);
        Assert.Equal(row.Status, read.Status);
        Assert.Equal(row.ContentType, read.ContentType);
        Assert.Equal(row.Body, read.Body); // sequence equality via IEnumerable overload
        Assert.Equal(row.FetchedAt, read.FetchedAt);
        Assert.Equal(row.ExpiresAt, read.ExpiresAt);
        Assert.Equal(row.ETag, read.ETag);
        Assert.Equal(row.LastModified, read.LastModified);
        Assert.Equal(row.Hits, read.Hits);

        store.BumpHits("k1");
        var updated = row with { Body = TestBytes.Of("v2"), ETag = "w/\"e2\"" };
        store.PutUpstream(updated);

        read = store.GetUpstream("k1");
        Assert.Equal("v2", TestBytes.Read(read!.Body));
        Assert.Equal("w/\"e2\"", read.ETag);
        Assert.Equal(1, read.Hits); // preserved across the upsert
        Assert.Null(store.GetUpstream("missing"));
    }

    [Fact]
    public void Items_keep_language_variants_separate()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        var en = new CachedItem("tmdb-movie-105", "movie", "tmdb", "105", "en-US", "{\"title\":\"Back to the Future\"}",
            Now, Now.AddHours(1), null);
        var de = en with { Lang = "de-DE", Json = "{\"title\":\"Zuruck in die Zukunft\"}" };

        store.PutItem(en);
        store.PutItem(de);

        Assert.Equal("{\"title\":\"Back to the Future\"}", store.GetItem("tmdb-movie-105", "en-US")!.Json);
        Assert.Equal("{\"title\":\"Zuruck in die Zukunft\"}", store.GetItem("tmdb-movie-105", "de-DE")!.Json);
        Assert.Null(store.GetItem("tmdb-movie-105", "fr-FR"));
        Assert.Null(store.GetItem("tmdb-movie-999", "en-US"));
    }

    [Fact]
    public void Urls_roundtrip()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        var url = new CachedUrl("abc123", "https://image.tmdb.org/t/p/original/poster.jpg", "im/abc123.jpg", 5120, Now);

        store.PutUrl(url);

        Assert.Equal(url, store.GetUrl("abc123"));
        Assert.Null(store.GetUrl("nope"));
    }

    [Fact]
    public void PurgeExpired_removes_only_expired_rows_and_never_urls()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        var clock = new FakeClock(Now);

        // fresh upstream + expired upstream
        store.PutUpstream(new CachedUpstreamRow("fresh", "https://x/fresh", 200, null, TestBytes.Of("f"),
            Now.AddMinutes(-1), Now.AddHours(1), null, null, 0));
        store.PutUpstream(new CachedUpstreamRow("expired", "https://x/expired", 200, null, TestBytes.Of("e"),
            Now.AddHours(-2), Now.AddHours(-1), null, null, 0));

        // fresh item + expired item
        store.PutItem(new CachedItem("fresh-item", "movie", "tmdb", "1", "en-US", "{}",
            Now.AddMinutes(-1), Now.AddHours(1), null));
        store.PutItem(new CachedItem("expired-item", "movie", "tmdb", "2", "en-US", "{}",
            Now.AddHours(-2), Now.AddHours(-1), null));

        // urls have no expiry and must survive
        store.PutUrl(new CachedUrl("img1", "https://img/1.jpg", "img/1.jpg", 10, Now.AddHours(-5)));

        var removed = store.PurgeExpired();

        Assert.Equal(2, removed);
        Assert.NotNull(store.GetUpstream("fresh"));
        Assert.Null(store.GetUpstream("expired"));
        Assert.NotNull(store.GetItem("fresh-item", "en-US"));
        Assert.Null(store.GetItem("expired-item", "en-US"));
        Assert.NotNull(store.GetUrl("img1"));
    }

    [Fact]
    public void Stats_report_entries_and_bytes()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.PutUpstream(new CachedUpstreamRow("k1", "https://x/1", 200, null, TestBytes.Of("hello"), Now, Now.AddHours(1), null, null, 0));
        store.PutUpstream(new CachedUpstreamRow("k2", "https://x/2", 200, null, TestBytes.Of("world!"), Now, Now.AddHours(1), null, null, 0));
        store.PutItem(new CachedItem("i1", "movie", "tmdb", "1", "en-US", "{}", Now, Now.AddHours(1), null));
        store.PutUrl(new CachedUrl("u1", "https://img/1.jpg", "img/1.jpg", 100, Now));

        var stats = store.GetStats();

        Assert.Equal(2, stats.UpstreamEntries);
        Assert.Equal(11, stats.UpstreamBytes); // "hello" + "world!"
        Assert.Equal(1, stats.ItemEntries);
        Assert.Equal(1, stats.UrlEntries);
    }

    private static string TempDbPath() =>
        Path.Combine(Path.GetTempPath(), $"metacache-{Guid.NewGuid():N}.db");
}
