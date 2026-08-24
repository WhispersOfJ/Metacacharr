using System.Globalization;
using Microsoft.Data.Sqlite;

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
    private const int SchemaVersion = 1;

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
            PRIMARY KEY (id, lang)
        );
        CREATE INDEX IF NOT EXISTS ix_items_source ON items(source, source_id);
        CREATE INDEX IF NOT EXISTS ix_items_kind_lang ON items(kind, lang);

        CREATE TABLE IF NOT EXISTS urls (
            id         TEXT PRIMARY KEY,
            url        TEXT NOT NULL,
            path       TEXT NOT NULL,
            size       INTEGER NOT NULL,
            fetched_at TEXT NOT NULL
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
            if (Convert.ToInt32(cmd.ExecuteScalar(), CultureInfo.InvariantCulture) >= SchemaVersion)
                return;

            cmd.CommandText = SchemaSql;
            cmd.ExecuteNonQuery();

            cmd.CommandText = $"PRAGMA user_version = {SchemaVersion};";
            cmd.ExecuteNonQuery();
        }
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
                SELECT id, kind, source, source_id, lang, json, fetched_at, expires_at, etag
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
                reader.IsDBNull(8) ? null : reader.GetString(8));
        }
    }

    public void PutItem(CachedItem item)
    {
        lock (_gate)
        {
            using var cmd = _connection.CreateCommand();
            cmd.CommandText = """
                INSERT INTO items (id, kind, source, source_id, lang, json, fetched_at, expires_at, etag)
                VALUES (@id, @kind, @source, @source_id, @lang, @json, @fetched_at, @expires_at, @etag)
                ON CONFLICT(id, lang) DO UPDATE SET
                    kind = excluded.kind, source = excluded.source, source_id = excluded.source_id,
                    json = excluded.json, fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at, etag = excluded.etag;
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
            cmd.ExecuteNonQuery();
        }
    }

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
