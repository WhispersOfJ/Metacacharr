using System.Globalization;
using Microsoft.Data.Sqlite;
using Metacache.Core.Matching;

namespace Metacache.Core.Cache;

/// <summary>
/// SQLite store for the three cache tables (DESIGN.md §7.4): `upstream_cache` (raw HTTP),
/// `items` (normalized metadata, keyed by id+lang) and `urls` (image assets).
///
/// Timestamps are persisted as ISO-8601 UTC strings ("O" format) so SQL comparisons and
/// the C# side agree. Schema is versioned with PRAGMA user_version.
/// Single connection, guarded by a lock — fine at this scale, WAL keeps readers/writers
/// out of each other's way for file-backed databases.
/// </summary>
public sealed class CacheStore : IDisposable
{
    // v2: match_overrides + unmatched tables (the manual match pin feature).
    // v3: items.title + items.year — the queryable search index (§19).
    // v4: items.thumb — the browse-list artwork hash (§21).
    // CREATE TABLE IF NOT EXISTS creates fresh schemas; ALTER TABLE in EnsureSchema
    // upgrades older databases in place (the version gate in the migration loop).
    private const int SchemaVersion = 4;

    private const string SchemaSql = """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;

        CREATE TABLE IF NOT EXISTS upstream_cache (
            key          TEXT PRIMARY KEY,
            url          TEXT NOT NULL,
            status       INTEGER NOT NULL,
            content_type TEXT,
            body         BLOB NOT NULL,
            fetched_at   TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            etag         TEXT,
            last_modified TEXT,
            hits         INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS ix_upstream_cache_expires ON upstream_cache(expires_at);

        CREATE TABLE IF NOT EXISTS items (
            id         TEXT NOT NULL,
            kind       TEXT NOT NULL,
            source     TEXT NOT NULL,
            source_id  TEXT NOT NULL,
            lang       TEXT NOT NULL,
            json       TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            etag       TEXT,
            title      TEXT,
            year       INTEGER,
            thumb      TEXT,
            PRIMARY KEY (id, lang)
        );
        CREATE INDEX IF NOT EXISTS ix_items_source ON items(source, source_id);
        CREATE INDEX IF NOT EXISTS ix_items_kind_lang ON items(kind, lang);
        CREATE INDEX IF NOT EXISTS ix_items_title ON items(title);

        CREATE TABLE IF NOT EXISTS urls (
            id         TEXT PRIMARY KEY,
            url        TEXT NOT NULL,
            path       TEXT NOT NULL,
            size       INTEGER NOT NULL,
            fetched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS match_overrides (
            key        TEXT PRIMARY KEY,
            kind       TEXT NOT NULL,
            target     TEXT NOT NULL,
            notes      TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS unmatched (
            key              TEXT PRIMARY KEY,
            kind             TEXT NOT NULL,
            title            TEXT,
            year             INTEGER,
            guid             TEXT,
            filename         TEXT,
            parent_title     TEXT,
            grandparent_title TEXT,
            idx              INTEGER,
            parent_index     INTEGER,
            air_date         TEXT,
            count            INTEGER NOT NULL DEFAULT 1,
            last_seen_at     TEXT NOT NULL
        );
        """;

    private readonly object _gate = new();
    private readonly SqliteConnection _connection;
    private readonly IClock _clock;

    public CacheStore(string dataSource, IClock? clock = null)
    {
        _clock = clock ?? SystemClock.Instance;
        var builder = new SqliteConnectionStringBuilder
        {
            DataSource = dataSource,
            Mode = SqliteOpenMode.ReadWriteCreate
        };
        _connection = new SqliteConnection(builder.ToString());
        _connection.Open();
        using var init = _connection.CreateCommand();
        init.CommandText = "PRAGMA busy_timeout = 5000;";
        init.ExecuteNonQuery();
        EnsureSchema();
    }

    private void EnsureSchema()
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "PRAGMA user_version;";
            int version = Convert.ToInt32(cmd.ExecuteScalar(), CultureInfo.InvariantCulture);
            if (version >= SchemaVersion)
                return;

            cmd.CommandText = SchemaSql;
            cmd.ExecuteNonQuery();

            // Stepwise upgrades for databases created by an older schema. Each step
            // guards on its own column so re-runs are idempotent.
            if (!ColumnExists("items", "title"))
            {
                cmd.CommandText = "ALTER TABLE items ADD COLUMN title TEXT;";
                cmd.ExecuteNonQuery();
            }
            if (!ColumnExists("items", "year"))
            {
                cmd.CommandText = "ALTER TABLE items ADD COLUMN year INTEGER;";
                cmd.ExecuteNonQuery();
            }
            if (!ColumnExists("items", "thumb"))
            {
                cmd.CommandText = "ALTER TABLE items ADD COLUMN thumb TEXT;";
                cmd.ExecuteNonQuery();
            }
            cmd.CommandText = "CREATE INDEX IF NOT EXISTS ix_items_title ON items(title);";
            cmd.ExecuteNonQuery();

            cmd.CommandText = $"PRAGMA user_version = {SchemaVersion};";
            cmd.ExecuteNonQuery();
        }
    }

    private bool ColumnExists(string table, string column)
    {
        using var cmd = _connection.CreateCommand();
        cmd.CommandText = $"SELECT COUNT(*) FROM pragma_table_info('{table}') WHERE name = @name;";
        cmd.Parameters.AddWithValue("@name", column);
        return Convert.ToInt32(cmd.ExecuteScalar(), CultureInfo.InvariantCulture) > 0;
    }

    // ---- upstream_cache ----

    public CachedUpstreamRow? GetUpstream(string key)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                SELECT key, url, status, content_type, body, fetched_at, expires_at, etag, last_modified, hits
                FROM upstream_cache WHERE key = @key;
                """;
            cmd.Parameters.AddWithValue("@key", key);
            using var reader = cmd.ExecuteReader();
            if (!reader.Read())
                return null;

            return new CachedUpstreamRow(
                reader.GetString(0),
                reader.GetString(1),
                reader.GetInt32(2),
                reader.IsDBNull(3) ? null : reader.GetString(3),
                reader.GetFieldValue<byte[]>(4),
                ParseTs(reader.GetString(5)),
                ParseTs(reader.GetString(6)),
                reader.IsDBNull(7) ? null : reader.GetString(7),
                reader.IsDBNull(8) ? null : ParseTs(reader.GetString(8)),
                reader.GetInt64(9));
        }
    }

    /// <summary>Upsert. On conflict all data fields are replaced but `hits` is preserved.</summary>
    public void PutUpstream(CachedUpstreamRow row)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                INSERT INTO upstream_cache
                    (key, url, status, content_type, body, fetched_at, expires_at, etag, last_modified, hits)
                VALUES (@key, @url, @status, @content_type, @body, @fetched_at, @expires_at, @etag, @last_modified, @hits)
                ON CONFLICT(key) DO UPDATE SET
                    url = excluded.url, status = excluded.status, content_type = excluded.content_type,
                    body = excluded.body, fetched_at = excluded.fetched_at, expires_at = excluded.expires_at,
                    etag = excluded.etag, last_modified = excluded.last_modified;
                """;
            cmd.Parameters.AddWithValue("@key", row.Key);
            cmd.Parameters.AddWithValue("@url", row.Url);
            cmd.Parameters.AddWithValue("@status", row.Status);
            cmd.Parameters.AddWithValue("@content_type", (object?)row.ContentType ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@body", row.Body);
            cmd.Parameters.AddWithValue("@fetched_at", Ts(row.FetchedAt));
            cmd.Parameters.AddWithValue("@expires_at", Ts(row.ExpiresAt));
            cmd.Parameters.AddWithValue("@etag", (object?)row.ETag ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@last_modified", row.LastModified is { } lm ? Ts(lm) : DBNull.Value);
            cmd.Parameters.AddWithValue("@hits", row.Hits);
            cmd.ExecuteNonQuery();
        }
    }

    public void BumpHits(string key)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "UPDATE upstream_cache SET hits = hits + 1 WHERE key = @key;";
            cmd.Parameters.AddWithValue("@key", key);
            cmd.ExecuteNonQuery();
        }
    }

    // ---- items ----

    public CachedItem? GetItem(string id, string lang)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                SELECT id, kind, source, source_id, lang, json, fetched_at, expires_at, etag, title, year, thumb
                FROM items WHERE id = @id AND lang = @lang;
                """;
            cmd.Parameters.AddWithValue("@id", id);
            cmd.Parameters.AddWithValue("@lang", lang);
            using var reader = cmd.ExecuteReader();
            if (!reader.Read())
                return null;

            return new CachedItem(
                reader.GetString(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.GetString(4),
                reader.GetString(5),
                ParseTs(reader.GetString(6)),
                ParseTs(reader.GetString(7)),
                reader.IsDBNull(8) ? null : reader.GetString(8),
                reader.IsDBNull(9) ? null : reader.GetString(9),
                reader.IsDBNull(10) ? null : reader.GetInt32(10),
                reader.IsDBNull(11) ? null : reader.GetString(11));
        }
    }

    public void PutItem(CachedItem item)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                INSERT INTO items (id, kind, source, source_id, lang, json, fetched_at, expires_at, etag, title, year, thumb)
                VALUES (@id, @kind, @source, @source_id, @lang, @json, @fetched_at, @expires_at, @etag, @title, @year, @thumb)
                ON CONFLICT(id, lang) DO UPDATE SET
                    kind = excluded.kind, source = excluded.source, source_id = excluded.source_id,
                    json = excluded.json, fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at, etag = excluded.etag,
                    title = excluded.title, year = excluded.year, thumb = excluded.thumb;
                """;
            cmd.Parameters.AddWithValue("@id", item.Id);
            cmd.Parameters.AddWithValue("@kind", item.Kind);
            cmd.Parameters.AddWithValue("@source", item.Source);
            cmd.Parameters.AddWithValue("@source_id", item.SourceId);
            cmd.Parameters.AddWithValue("@lang", item.Lang);
            cmd.Parameters.AddWithValue("@json", item.Json);
            cmd.Parameters.AddWithValue("@fetched_at", Ts(item.FetchedAt));
            cmd.Parameters.AddWithValue("@expires_at", Ts(item.ExpiresAt));
            cmd.Parameters.AddWithValue("@etag", (object?)item.ETag ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@title", (object?)item.Title ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@year", (object?)item.Year ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@thumb", (object?)item.Thumb ?? DBNull.Value);
            cmd.ExecuteNonQuery();
        }
    }

    /// <summary>
    /// Queryable cache index (§19/§21): filter the normalized items by kind, title
    /// substring (case-insensitive LIKE, with %/_/\ escaped), a set of source ids (used
    /// for guid-resolved searches), year and freshness; order by title
    /// (case-insensitive) or most-recently-fetched. Capped by
    /// <see cref="ItemSearch.Limit"/> at <see cref="ItemSearch.Offset"/>;
    /// <see cref="ItemSearchResult.Total"/> is the count without limit/offset.
    /// </summary>
    public ItemSearchResult SearchItems(ItemSearch search, DateTimeOffset now)
    {
        lock (_gate)
        {
            var where = new List<string>();
            var parameters = new List<(string Name, object? Value)>();

            if (search.Kinds is { Count: > 0 } kinds)
            {
                var placeholders = string.Join(", ", kinds.Select((_, i) => $"@kind{i}"));
                where.Add($"kind IN ({placeholders})");
                for (int i = 0; i < kinds.Count; i++)
                    parameters.Add(($"@kind{i}", kinds[i]));
            }
            if (search.TitleLike is not null)
            {
                where.Add("title LIKE @q ESCAPE '\\'");
                parameters.Add(("@q", $"%{EscapeLike(search.TitleLike)}%"));
            }
            if (search.SourceIds is { Count: > 0 } ids)
            {
                var placeholders = string.Join(", ", ids.Select((_, i) => $"@sid{i}"));
                where.Add($"source_id IN ({placeholders})");
                for (int i = 0; i < ids.Count; i++)
                    parameters.Add(($"@sid{i}", ids[i]));
            }
            if (search.Year is { } year)
            {
                where.Add("year = @year");
                parameters.Add(("@year", year));
            }
            if (search.FreshOnly)
            {
                where.Add("expires_at > @now");
                parameters.Add(("@now", Ts(now)));
            }

            string whereSql = where.Count == 0 ? "" : $" WHERE {string.Join(" AND ", where)}";
            string orderSql = search.RecentFirst ? "fetched_at DESC, id" : "title COLLATE NOCASE, id";

            using var countCmd = _connection.CreateCommand();
            countCmd.CommandText = $"SELECT COUNT(*) FROM items{whereSql};";
            foreach ((string name, object? value) in parameters)
                countCmd.Parameters.AddWithValue(name, value);
            int total = Convert.ToInt32(countCmd.ExecuteScalar(), CultureInfo.InvariantCulture);

            var list = new List<CachedItem>();
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = $"""
                SELECT id, kind, source, source_id, lang, json, fetched_at, expires_at, etag, title, year, thumb
                FROM items{whereSql}
                ORDER BY {orderSql}
                LIMIT @limit OFFSET @offset;
                """;
            cmd.Parameters.AddWithValue("@limit", Math.Max(1, search.Limit));
            cmd.Parameters.AddWithValue("@offset", Math.Max(0, search.Offset));
            foreach ((string name, object? value) in parameters)
                cmd.Parameters.AddWithValue(name, value);
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                list.Add(new CachedItem(
                    reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3),
                    reader.GetString(4), reader.GetString(5), ParseTs(reader.GetString(6)),
                    ParseTs(reader.GetString(7)), reader.IsDBNull(8) ? null : reader.GetString(8),
                    reader.IsDBNull(9) ? null : reader.GetString(9),
                    reader.IsDBNull(10) ? null : reader.GetInt32(10),
                    reader.IsDBNull(11) ? null : reader.GetString(11)));
            }
            return new ItemSearchResult(list, total);
        }
    }

    /// <summary>Escapes %, _ and \ so a user query is matched literally (LIKE ... ESCAPE '\').</summary>
    private static string EscapeLike(string value) =>
        value.Replace("\\", "\\\\", StringComparison.Ordinal)
            .Replace("%", "\\%", StringComparison.Ordinal)
            .Replace("_", "\\_", StringComparison.Ordinal);

    // ---- urls (image assets) ----

    public CachedUrl? GetUrl(string hash)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "SELECT id, url, path, size, fetched_at FROM urls WHERE id = @id;";
            cmd.Parameters.AddWithValue("@id", hash);
            using var reader = cmd.ExecuteReader();
            if (!reader.Read())
                return null;

            return new CachedUrl(
                reader.GetString(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetInt64(3),
                ParseTs(reader.GetString(4)));
        }
    }

    public void PutUrl(CachedUrl url)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                INSERT INTO urls (id, url, path, size, fetched_at)
                VALUES (@id, @url, @path, @size, @fetched_at)
                ON CONFLICT(id) DO UPDATE SET
                    url = excluded.url, path = excluded.path, size = excluded.size, fetched_at = excluded.fetched_at;
                """;
            cmd.Parameters.AddWithValue("@id", url.Hash);
            cmd.Parameters.AddWithValue("@url", url.Url);
            cmd.Parameters.AddWithValue("@path", url.Path);
            cmd.Parameters.AddWithValue("@size", url.Size);
            cmd.Parameters.AddWithValue("@fetched_at", Ts(url.FetchedAt));
            cmd.ExecuteNonQuery();
        }
    }

    public long SumUrlBytes()
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "SELECT COALESCE(SUM(size), 0) FROM urls;";
            return Convert.ToInt64(cmd.ExecuteScalar(), CultureInfo.InvariantCulture);
        }
    }

    /// <summary>Oldest url rows first (fetched_at, then id) — for total-cap eviction.</summary>
    public IReadOnlyList<CachedUrl> GetOldestUrls(int limit)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                SELECT id, url, path, size, fetched_at FROM urls
                ORDER BY fetched_at ASC, id ASC LIMIT @limit;
                """;
            cmd.Parameters.AddWithValue("@limit", limit);

            var rows = new List<CachedUrl>();
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                rows.Add(new CachedUrl(
                    reader.GetString(0),
                    reader.GetString(1),
                    reader.GetString(2),
                    reader.GetInt64(3),
                    ParseTs(reader.GetString(4))));
            }
            return rows;
        }
    }

    public void DeleteUrl(string hash)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "DELETE FROM urls WHERE id = @id;";
            cmd.Parameters.AddWithValue("@id", hash);
            cmd.ExecuteNonQuery();
        }
    }

    // ---- maintenance / stats ----

    /// <summary>Deletes expired rows from upstream_cache and items (urls have no expiry).</summary>
    public int PurgeExpired()
    {
        lock (_gate)
        {
            string now = Ts(_clock.UtcNow);
            int removed = 0;
            removed += ExecuteDelete("DELETE FROM upstream_cache WHERE expires_at <= @now;", now);
            removed += ExecuteDelete("DELETE FROM items WHERE expires_at <= @now;", now);
            return removed;
        }
    }

    /// <summary>Item counts by kind (movie/show/season/episode) for the /metrics dashboard.</summary>
    public IReadOnlyDictionary<string, int> CountItemsByKind()
    {
        lock (_gate)
        {
            var counts = new Dictionary<string, int>(StringComparer.Ordinal);
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "SELECT kind, COUNT(*) FROM items GROUP BY kind;";
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
                counts[reader.GetString(0)] = reader.GetInt32(1);
            return counts;
        }
    }

    public CacheStats GetStats()
    {
        lock (_gate)
        {
            int upstream = 0;
            long upstreamBytes = 0;
            int items = 0;
            int urls = 0;

            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT COUNT(*), COALESCE(SUM(LENGTH(body)), 0) FROM upstream_cache;";
                using var reader = cmd.ExecuteReader();
                reader.Read();
                upstream = reader.GetInt32(0);
                upstreamBytes = reader.GetInt64(1);
            }

            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT COUNT(*) FROM items;";
                items = Convert.ToInt32(cmd.ExecuteScalar(), CultureInfo.InvariantCulture);
            }

            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT COUNT(*) FROM urls;";
                urls = Convert.ToInt32(cmd.ExecuteScalar(), CultureInfo.InvariantCulture);
            }

            return new CacheStats(upstream, upstreamBytes, items, urls);
        }
    }

    // ---- match_overrides (manual pins, DESIGN.md §15.10) ----

    public MatchOverride? GetOverride(string key)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "SELECT key, kind, target, notes, created_at FROM match_overrides WHERE key = @key;";
            cmd.Parameters.AddWithValue("@key", key);
            using var reader = cmd.ExecuteReader();
            if (!reader.Read())
                return null;
            return new MatchOverride(
                reader.GetString(0), reader.GetString(1), reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3), reader.GetString(4));
        }
    }

    /// <summary>Upsert — a re-pin with the same key replaces the target and notes.</summary>
    public void PutOverride(MatchOverride entry)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                INSERT INTO match_overrides (key, kind, target, notes, created_at)
                VALUES (@key, @kind, @target, @notes, @created_at)
                ON CONFLICT(key) DO UPDATE SET
                    kind = excluded.kind, target = excluded.target, notes = excluded.notes;
                """;
            cmd.Parameters.AddWithValue("@key", entry.Key);
            cmd.Parameters.AddWithValue("@kind", entry.Kind);
            cmd.Parameters.AddWithValue("@target", entry.Target);
            cmd.Parameters.AddWithValue("@notes", (object?)entry.Notes ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@created_at", entry.CreatedAt);
            cmd.ExecuteNonQuery();
        }
    }

    public bool DeleteOverride(string key)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "DELETE FROM match_overrides WHERE key = @key;";
            cmd.Parameters.AddWithValue("@key", key);
            return cmd.ExecuteNonQuery() > 0;
        }
    }

    public IReadOnlyList<MatchOverride> ListOverrides()
    {
        lock (_gate)
        {
            var list = new List<MatchOverride>();
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "SELECT key, kind, target, notes, created_at FROM match_overrides ORDER BY created_at;";
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
                list.Add(new MatchOverride(
                    reader.GetString(0), reader.GetString(1), reader.GetString(2),
                    reader.IsDBNull(3) ? null : reader.GetString(3), reader.GetString(4)));
            return list;
        }
    }

    // ---- unmatched (auto-match failures, DESIGN.md §15.10) ----

    /// <summary>Records a failed auto-match hint, bumping the counter when the same key recurs.</summary>
    public void RecordUnmatched(MatchHint hint) =>
        RecordUnmatched(UnmatchedEntry.FromHint(hint, _clock.UtcNow));

    /// <summary>Records a failed auto-match, bumping the counter when the same key recurs.</summary>
    public void RecordUnmatched(UnmatchedEntry entry)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                INSERT INTO unmatched
                    (key, kind, title, year, guid, filename, parent_title, grandparent_title,
                     idx, parent_index, air_date, count, last_seen_at)
                VALUES (@key, @kind, @title, @year, @guid, @filename, @parent_title, @grandparent_title,
                        @idx, @parent_index, @air_date, 1, @last_seen_at)
                ON CONFLICT(key) DO UPDATE SET
                    count = count + 1, last_seen_at = excluded.last_seen_at;
                """;
            cmd.Parameters.AddWithValue("@key", entry.Key);
            cmd.Parameters.AddWithValue("@kind", entry.Kind);
            cmd.Parameters.AddWithValue("@title", (object?)entry.Title ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@year", (object?)entry.Year ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@guid", (object?)entry.Guid ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@filename", (object?)entry.Filename ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@parent_title", (object?)entry.ParentTitle ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@grandparent_title", (object?)entry.GrandparentTitle ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@idx", (object?)entry.Index ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@parent_index", (object?)entry.ParentIndex ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@air_date", (object?)entry.AirDate ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@last_seen_at", entry.LastSeenAt);
            cmd.ExecuteNonQuery();
        }
    }

    public IReadOnlyList<UnmatchedEntry> ListUnmatched()
    {
        lock (_gate)
        {
            var list = new List<UnmatchedEntry>();
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                SELECT key, kind, title, year, guid, filename, parent_title, grandparent_title,
                       idx, parent_index, air_date, count, last_seen_at
                FROM unmatched ORDER BY last_seen_at DESC;
                """;
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
                list.Add(new UnmatchedEntry(
                    reader.GetString(0), reader.GetString(1),
                    reader.IsDBNull(2) ? null : reader.GetString(2),
                    reader.IsDBNull(3) ? null : reader.GetInt32(3),
                    reader.IsDBNull(4) ? null : reader.GetString(4),
                    reader.IsDBNull(5) ? null : reader.GetString(5),
                    reader.IsDBNull(6) ? null : reader.GetString(6),
                    reader.IsDBNull(7) ? null : reader.GetString(7),
                    reader.IsDBNull(8) ? null : reader.GetInt32(8),
                    reader.IsDBNull(9) ? null : reader.GetInt32(9),
                    reader.IsDBNull(10) ? null : reader.GetString(10),
                    reader.GetInt32(11), reader.GetString(12)));
            return list;
        }
    }

    public bool DeleteUnmatched(string key)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "DELETE FROM unmatched WHERE key = @key;";
            cmd.Parameters.AddWithValue("@key", key);
            return cmd.ExecuteNonQuery() > 0;
        }
    }

    public int ClearUnmatched()
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = "DELETE FROM unmatched;";
            return cmd.ExecuteNonQuery();
        }
    }

    private int ExecuteDelete(string sql, string now)
    {
        using var cmd = _connection.CreateCommand();
        cmd.CommandText = sql;
        cmd.Parameters.AddWithValue("@now", now);
        return cmd.ExecuteNonQuery();
    }

    private static string Ts(DateTimeOffset value) =>
        value.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture);

    private static DateTimeOffset ParseTs(string value) =>
        DateTimeOffset.Parse(value, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind);

    public void Dispose()
    {
        lock (_gate)
        {
            _connection.Dispose();
        }
    }
}
