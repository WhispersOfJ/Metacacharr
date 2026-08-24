using System.Globalization;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;

namespace Metacache.Host.Tests.Cache;

public class CacheIndexTests
{
    private static readonly DateTimeOffset Now = DateTimeOffset.Parse("2026-08-24T12:00:00+00:00", CultureInfo.InvariantCulture);

    [Fact]
    public void Put_and_get_roundtrip_title_year_and_thumb()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.PutItem(Item("movie-105", "movie", "105", "Back to the Future", 1985, thumb: "/img/abc"));

        CachedItem read = store.GetItem("movie-105", "en-US")!;
        Assert.Equal("Back to the Future", read.Title);
        Assert.Equal(1985, read.Year);
        Assert.Equal("/img/abc", read.Thumb);
    }

    [Fact]
    public void Search_filters_by_kind_and_title_substring()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        Seed(store);

        var all = store.SearchItems(new ItemSearch(), Now);
        Assert.Equal(3, all.Total);
        Assert.Equal(3, all.Items.Count);

        var movies = store.SearchItems(new ItemSearch(Kinds: ["movie"]), Now);
        Assert.Equal(2, movies.Total);

        var partTwo = store.SearchItems(new ItemSearch(TitleLike: "part ii"), Now);
        Assert.Equal("movie-165", Assert.Single(partTwo.Items).Id);

        var future = store.SearchItems(new ItemSearch(TitleLike: "FUTURE"), Now);
        Assert.Equal(2, future.Total); // case-insensitive
    }

    [Fact]
    public void Search_escapes_like_wildcards_in_the_query()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.PutItem(Item("movie-1", "movie", "1", "100% Lover", 1990));
        store.PutItem(Item("movie-2", "movie", "2", "The Other Film", 1991));

        var percent = store.SearchItems(new ItemSearch(TitleLike: "%"), Now);
        Assert.Equal(1, percent.Total); // literal '%', not a wildcard
        Assert.Equal("100% Lover", Assert.Single(percent.Items).Title);

        var underscore = store.SearchItems(new ItemSearch(TitleLike: "_"), Now);
        Assert.Equal(0, underscore.Total);
    }

    [Fact]
    public void Fresh_only_excludes_expired_items()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.PutItem(Item("movie-1", "movie", "1", "Fresh", 1990, expires: Now.AddHours(1)));
        store.PutItem(Item("movie-2", "movie", "2", "Stale", 1991, expires: Now.AddHours(-1)));

        var fresh = store.SearchItems(new ItemSearch(FreshOnly: true), Now);
        Assert.Equal("movie-1", Assert.Single(fresh.Items).Id);

        var all = store.SearchItems(new ItemSearch(), Now);
        Assert.Equal(2, all.Total);
    }

    [Fact]
    public void Source_ids_filter_and_limit_reports_the_unlimited_total()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        Seed(store);

        var byId = store.SearchItems(new ItemSearch(SourceIds: ["105", "15260"]), Now);
        Assert.Equal(2, byId.Total);

        var page = store.SearchItems(new ItemSearch(Limit: 2), Now);
        Assert.Equal(2, page.Items.Count);
        Assert.Equal(3, page.Total);
    }

    [Fact]
    public void A_v2_database_upgrades_in_place_with_title_and_year_columns()
    {
        string dbPath = Path.Combine(Path.GetTempPath(), $"metacache-v2-{Guid.NewGuid():N}.db");
        try
        {
            // Build a v2 database: the old items shape (no title/year) at user_version 2.
            using (var conn = new Microsoft.Data.Sqlite.SqliteConnection($"Data Source={dbPath}"))
            {
                conn.Open();
                using var cmd = conn.CreateCommand();
                cmd.CommandText = """
                    CREATE TABLE items (
                        id TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL,
                        source_id TEXT NOT NULL, lang TEXT NOT NULL, json TEXT NOT NULL,
                        fetched_at TEXT NOT NULL, expires_at TEXT NOT NULL, etag TEXT,
                        PRIMARY KEY (id, lang));
                    PRAGMA user_version = 2;
                    """;
                cmd.ExecuteNonQuery();
            }

            // Reopening with the current store must ALTER the table and accept title/year.
            using var store = new CacheStore(dbPath, new FakeClock(Now));
            store.PutItem(Item("movie-105", "movie", "105", "Back to the Future", 1985));

            CachedItem read = store.GetItem("movie-105", "en-US")!;
            Assert.Equal("Back to the Future", read.Title);
            Assert.Equal(1985, read.Year);
            Assert.Equal(1, store.SearchItems(new ItemSearch(TitleLike: "future"), Now).Total);
        }
        finally
        {
            File.Delete(dbPath);
            File.Delete(dbPath + "-wal");
            File.Delete(dbPath + "-shm");
        }
    }

    [Fact]
    public void Search_filters_by_year_and_pages_with_offset()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        Seed(store);

        var byYear = store.SearchItems(new ItemSearch(Year: 1985), Now);
        Assert.Equal("movie-105", Assert.Single(byYear.Items).Id);

        var page = store.SearchItems(new ItemSearch(Limit: 1, Offset: 1), Now);
        Assert.Single(page.Items);
        Assert.Equal(3, page.Total); // offset doesn't change the total
    }

    [Fact]
    public void Search_recent_first_orders_by_fetched_at_desc()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.PutItem(Item("movie-1", "movie", "1", "Old", 1990, fetchedAt: Now.AddDays(-2)));
        store.PutItem(Item("movie-2", "movie", "2", "New", 1991, fetchedAt: Now));

        var result = store.SearchItems(new ItemSearch(RecentFirst: true), Now);
        Assert.Equal(["movie-2", "movie-1"], result.Items.Select(i => i.Id));
    }

    [Fact]
    public void Search_sorts_by_title_case_insensitively()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.PutItem(Item("movie-1", "movie", "1", "zombieland", 2009));
        store.PutItem(Item("movie-2", "movie", "2", "Alien", 1979));
        store.PutItem(Item("movie-3", "movie", "3", "brazil", 1985));

        var result = store.SearchItems(new ItemSearch(), Now);
        Assert.Equal(["Alien", "brazil", "zombieland"], result.Items.Select(i => i.Title));
    }

    private static void Seed(CacheStore store)
    {
        store.PutItem(Item("movie-105", "movie", "105", "Back to the Future", 1985));
        store.PutItem(Item("movie-165", "movie", "165", "Back to the Future Part II", 1989));
        store.PutItem(Item("show-15260", "show", "15260", "Adventure Time", 2010));
    }

    private static CachedItem Item(string id, string kind, string sourceId, string? title, int? year,
        DateTimeOffset? expires = null, DateTimeOffset? fetchedAt = null, string? thumb = null) =>
        new(id, kind, "tmdb", sourceId, "en-US", "{}", fetchedAt ?? Now, expires ?? Now.AddDays(1), null, title, year, thumb);
}
