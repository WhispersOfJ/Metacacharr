using Metacache.Core.Matching;

namespace Metacache.Host.Tests.Matching;

public class TvMatchScorerTests
{
    private static MatchCandidate Season(string id, string show, int season, double popularity = 100)
        => new(id, $"Season {season}", null, null, "en", popularity, false, [],
            ParentTitle: show, Index: season);

    private static MatchCandidate Episode(string id, string show, int season, int episode,
        double popularity = 100, string? airDate = null)
        => new(id, $"Episode {episode}", null, null, "en", popularity, false, [],
            ParentTitle: show, Index: episode, ParentIndex: season, AirDate: airDate);

    private static MatchHint SeasonHint(string? show = null, int? index = null, string? filename = null, bool manual = false)
        => new(null, null, filename, [], manual, false, null,
            Kind: MatchKind.Season, ParentTitle: show, Index: index);

    private static MatchHint EpisodeHint(string? show = null, int? season = null, int? episode = null,
        string? airDate = null, string? filename = null, bool manual = false)
        => new(null, null, filename, [], manual, false, null,
            Kind: MatchKind.Episode, GrandparentTitle: show, ParentIndex: season, Index: episode, AirDate: airDate);

    [Fact]
    public void Season_auto_matches_exact_show_and_index()
    {
        var hint = SeasonHint("Adventure Time", index: 1);
        var candidates = new[]
        {
            Season("s2", "Adventure Time", 2),
            Season("bb1", "Breaking Bad", 1),
            Season("s1", "Adventure Time", 1)
        };

        ScoredMatch best = Assert.Single(MatchScorer.Score(hint, candidates));

        Assert.Equal("s1", best.Candidate.Id);
        Assert.Equal(0.864, best.Score, 3);
    }

    [Fact]
    public void Season_wrong_index_is_not_auto_matched()
    {
        var hint = SeasonHint("Adventure Time", index: 1);
        var candidates = new[] { Season("s2", "Adventure Time", 2) };

        Assert.Empty(MatchScorer.Score(hint, candidates));
    }

    [Fact]
    public void Season_manual_ranks_correct_season_first()
    {
        var hint = SeasonHint("Adventure Time", index: 1, manual: true);
        var candidates = new[]
        {
            Season("s2", "Adventure Time", 2),
            Season("bb1", "Breaking Bad", 1),
            Season("s1", "Adventure Time", 1)
        };

        var results = MatchScorer.Score(hint, candidates);

        Assert.Equal(3, results.Count);
        Assert.Equal("s1", results[0].Candidate.Id);
        Assert.All(results, r => Assert.True(r.Score >= MatchPolicy.Default.ManualMinScore));
    }

    [Fact]
    public void Episode_auto_matches_by_show_season_and_episode()
    {
        var hint = EpisodeHint("Adventure Time", season: 1, episode: 2);
        var candidates = new[]
        {
            Episode("e13", "Adventure Time", 1, 3),
            Episode("e22", "Adventure Time", 2, 2),
            Episode("other", "Breaking Bad", 1, 2),
            Episode("e12", "Adventure Time", 1, 2)
        };

        ScoredMatch best = Assert.Single(MatchScorer.Score(hint, candidates));

        Assert.Equal("e12", best.Candidate.Id);
    }

    [Fact]
    public void Episode_wrong_show_is_not_auto_matched()
    {
        var hint = EpisodeHint("Adventure Time", season: 1, episode: 2);
        var candidates = new[] { Episode("other", "Breaking Bad", 1, 2) };

        Assert.Empty(MatchScorer.Score(hint, candidates));
    }

    [Fact]
    public void Episode_matches_by_air_date_when_indices_are_missing()
    {
        var hint = EpisodeHint("Adventure Time", airDate: "2016-03-26");
        var candidates = new[]
        {
            Episode("d2", "Adventure Time", 8, 2, airDate: "2016-04-02"),
            Episode("d1", "Adventure Time", 8, 1, airDate: "2016-03-26")
        };

        ScoredMatch best = Assert.Single(MatchScorer.Score(hint, candidates));

        Assert.Equal("d1", best.Candidate.Id);
    }

    [Fact]
    public void Episode_filename_sxxeyy_supplies_structure_hint()
    {
        var hint = EpisodeHint("Adventure Time", filename: "Adventure.Time.S01E01.mkv");
        var candidates = new[]
        {
            Episode("b", "Adventure Time", 1, 2),
            Episode("a", "Adventure Time", 1, 1)
        };

        ScoredMatch best = Assert.Single(MatchScorer.Score(hint, candidates));

        Assert.Equal("a", best.Candidate.Id);
    }

    [Fact]
    public void Season_filename_season_n_supplies_structure_hint()
    {
        var hint = SeasonHint("Adventure Time", filename: "Adventure Time Season 1.mkv");
        var candidates = new[]
        {
            Season("s2", "Adventure Time", 2),
            Season("s1", "Adventure Time", 1)
        };

        ScoredMatch best = Assert.Single(MatchScorer.Score(hint, candidates));

        Assert.Equal("s1", best.Candidate.Id);
    }
}
