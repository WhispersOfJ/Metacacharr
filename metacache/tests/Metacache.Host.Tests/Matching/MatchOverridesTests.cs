using System.Globalization;
using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Host.Tests.Cache;

namespace Metacache.Host.Tests.Matching;

public class MatchOverridesTests
{
    private static readonly DateTimeOffset Now = DateTimeOffset.Parse("2026-08-24T12:00:00+00:00", CultureInfo.InvariantCulture);

    // ---- key derivation (MatchOverrideKeys.ForHint) ----

    [Fact]
    public void ForHint_uses_the_guid_when_present()
    {
        var hint = MovieHint() with { ExternalGuids = ["imdb://tt0088763"] };

        Assert.Equal("imdb://tt0088763", MatchOverrideKeys.ForHint(hint));
    }

    [Fact]
    public void ForHint_normalizes_title_and_year_for_a_movie()
    {
        var hint = MovieHint();

        Assert.Equal("movie:back to the future:1985", MatchOverrideKeys.ForHint(hint));
    }

    [Fact]
    public void ForHint_collapses_whitespace_and_lowercases()
    {
        var hint = MovieHint() with { Title = "  Back   TO  the FUTURE ", Year = 1985 };

        Assert.Equal("movie:back to the future:1985", MatchOverrideKeys.ForHint(hint));
    }

    [Fact]
    public void ForHint_uses_parent_title_for_season_and_grandparent_for_episode()
    {
        var season = MatchHint.Empty with
        {
            Kind = MatchKind.Season,
            ParentTitle = "Breaking Bad",
            Year = 2008,
            Index = 1
        };
        Assert.Equal("season:breaking bad:2008", MatchOverrideKeys.ForHint(season));

        var episode = MatchHint.Empty with
        {
            Kind = MatchKind.Episode,
            GrandparentTitle = "Breaking Bad",
            ParentIndex = 1,
            Index = 1
        };
        Assert.Equal("episode:breaking bad:", MatchOverrideKeys.ForHint(episode));
    }

    // ---- store persistence (match_overrides) ----

    [Fact]
    public void Override_roundtrips_and_missing_key_returns_null()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        Assert.Null(store.GetOverride("movie:back to the future:1985"));

        store.PutOverride(Override("movie:back to the future:1985", "tmdb-movie-165", "wrong year in plex"));

        MatchOverride? read = store.GetOverride("movie:back to the future:1985");
        Assert.NotNull(read);
        Assert.Equal("movie:back to the future:1985", read.Key);
        Assert.Equal("movie", read.Kind);
        Assert.Equal("tmdb-movie-165", read.Target);
        Assert.Equal("wrong year in plex", read.Notes);
        Assert.Equal(Now.ToString("O", CultureInfo.InvariantCulture), read.CreatedAt);
    }

    [Fact]
    public void Re_pinning_the_same_key_replaces_target_and_notes()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.PutOverride(Override("k1", "tmdb-movie-105", "first"));
        store.PutOverride(Override("k1", "tmdb-movie-165", "corrected"));

        MatchOverride read = store.GetOverride("k1")!;
        Assert.Equal("tmdb-movie-165", read.Target);
        Assert.Equal("corrected", read.Notes);
        Assert.Single(store.ListOverrides());
    }

    [Fact]
    public void Delete_override_removes_it_and_reports_whether_it_existed()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.PutOverride(Override("k1", "tmdb-movie-105", null));

        Assert.True(store.DeleteOverride("k1"));
        Assert.False(store.DeleteOverride("k1"));
        Assert.Empty(store.ListOverrides());
    }

    // ---- store persistence (unmatched) ----

    [Fact]
    public void Recording_an_unmatched_hint_captures_context_and_bumps_on_recurrence()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        var hint = MatchHint.Empty with
        {
            Kind = MatchKind.Episode,
            Title = "Pilot",
            GrandparentTitle = "Breaking Bad",
            ParentIndex = 1,
            Index = 1,
            AirDate = "2008-01-20",
            ExternalGuids = ["imdb://tt0903747"]
        };

        store.RecordUnmatched(hint);
        store.RecordUnmatched(hint);

        UnmatchedEntry entry = Assert.Single(store.ListUnmatched());
        Assert.Equal("imdb://tt0903747", entry.Key);
        Assert.Equal("episode", entry.Kind);
        Assert.Equal("Pilot", entry.Title);
        Assert.Equal("Breaking Bad", entry.GrandparentTitle);
        Assert.Equal(1, entry.ParentIndex);
        Assert.Equal(1, entry.Index);
        Assert.Equal("2008-01-20", entry.AirDate);
        Assert.Equal(2, entry.Count);
    }

    [Fact]
    public void Delete_and_clear_unmatched()
    {
        using var store = new CacheStore(":memory:", new FakeClock(Now));
        store.RecordUnmatched(MovieHint());

        Assert.True(store.DeleteUnmatched("movie:back to the future:1985"));
        Assert.False(store.DeleteUnmatched("movie:back to the future:1985"));

        store.RecordUnmatched(MovieHint());
        store.RecordUnmatched(MatchHint.Empty with { Title = "Other" });
        Assert.Equal(2, store.ClearUnmatched());
        Assert.Empty(store.ListUnmatched());
    }

    private static MatchHint MovieHint() =>
        MatchHint.Empty with { Title = "Back to the Future", Year = 1985 };

    private static MatchOverride Override(string key, string target, string? notes) =>
        new(key, "movie", target, notes, Now.ToString("O", CultureInfo.InvariantCulture));
}
