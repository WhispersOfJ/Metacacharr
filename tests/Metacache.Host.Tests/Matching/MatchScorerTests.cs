using Metacache.Core.Matching;

namespace Metacache.Host.Tests.Matching;

public class MatchScorerTests
{
    private static MatchCandidate Candidate(
        string id, string title, int? year, double popularity = 100,
        bool adult = false, string? lang = "en", IReadOnlyList<string>? external = null, string? originalTitle = null)
        => new(id, title, originalTitle, year, lang, popularity, adult, external ?? []);

    private static MatchHint Hint(
        string? title = null, int? year = null, string? filename = null,
        bool manual = false, string? language = null, bool includeAdult = false, params string[] guids)
        => new(title, year, filename, guids, manual, includeAdult, language);

    [Fact]
    public void Exact_external_guid_overrides_all_other_signals()
    {
        var hint = Hint("Completely Different Title", 2020, guids: "imdb://tt0088763");
        var candidates = new[]
        {
            Candidate("wrong", "Wrong Movie", 2020, popularity: 1),
            Candidate("right", "Back to the Future", 1985, popularity: 100,
                external: ["imdb://tt0088763"])
        };

        ScoredMatch best = Assert.Single(MatchScorer.Score(hint, candidates));

        Assert.Equal("right", best.Candidate.Id);
        Assert.Equal(1.0, best.Score, 6);
        Assert.True(best.Breakdown.GuidExact);
    }

    [Fact]
    public void Auto_match_prefers_exact_title_and_year()
    {
        var hint = Hint("Back to the Future", 1985);
        var candidates = new[]
        {
            Candidate("wrong-year", "Back to the Future", 2015),
            Candidate("right", "Back to the Future", 1985)
        };

        ScoredMatch best = Assert.Single(MatchScorer.Score(hint, candidates));

        Assert.Equal("right", best.Candidate.Id);
        Assert.Equal(0.839, best.Score, 3);
    }

    [Fact]
    public void Auto_match_returns_nothing_for_wrong_year()
    {
        var hint = Hint("Back to the Future", 1985);
        var candidates = new[] { Candidate("remake", "Back to the Future", 2015) };

        Assert.Empty(MatchScorer.Score(hint, candidates));
        Assert.Null(MatchScorer.BestMatch(hint, candidates));
    }

    [Fact]
    public void Manual_returns_ranked_list_above_floor()
    {
        var hint = Hint("Back to the Future", 1985, manual: true);
        var candidates = new[]
        {
            Candidate("a", "Back to the Future", 1985, popularity: 100),
            Candidate("b", "Back to the Future", 2015, popularity: 200),
            Candidate("c", "Total Recall", 1985, popularity: 100)
        };

        var results = MatchScorer.Score(hint, candidates);

        Assert.Equal(["a", "b", "c"], results.Select(r => r.Candidate.Id));
        Assert.All(results, r => Assert.True(r.Score >= MatchPolicy.Default.ManualMinScore));
        Assert.True(results[0].Score > results[1].Score);
        Assert.True(results[1].Score > results[2].Score);
    }

    [Fact]
    public void Filename_year_corrects_missing_hint_year()
    {
        var hint = Hint("Back to the Future", filename: "Movies/Back.to.the.Future.1985.1080p.BluRay.mkv");
        var candidates = new[]
        {
            Candidate("remake", "Back to the Future", 2015),
            Candidate("original", "Back to the Future", 1985)
        };

        ScoredMatch best = Assert.Single(MatchScorer.Score(hint, candidates));

        Assert.Equal("original", best.Candidate.Id);
    }

    [Fact]
    public void Adult_candidates_are_filtered_unless_requested()
    {
        var candidates = new[]
        {
            Candidate("normal", "Some Movie", 2000),
            Candidate("adult", "Some Movie", 2000, adult: true)
        };

        var without = MatchScorer.Score(Hint("Some Movie", 2000, manual: true), candidates);
        Assert.Equal("normal", Assert.Single(without).Candidate.Id);

        var with = MatchScorer.Score(Hint("Some Movie", 2000, manual: true, includeAdult: true), candidates);
        Assert.Equal(2, with.Count);
        Assert.Contains("adult", with.Select(r => r.Candidate.Id));
    }

    [Fact]
    public void Language_bonus_prefers_matching_original_language()
    {
        var candidates = new[]
        {
            Candidate("en", "Coco", 2017, lang: "en"),
            Candidate("es", "Coco", 2017, lang: "es")
        };

        var results = MatchScorer.Score(Hint("Coco", 2017, manual: true, language: "es-MX"), candidates);

        Assert.Equal("es", results[0].Candidate.Id);
        Assert.Equal(results[1].Score, results[0].Score - MatchPolicy.Default.LanguageBonus, 6);
    }

    [Fact]
    public void Popularity_ranks_more_popular_candidates_first_when_otherwise_equal()
    {
        var candidates = new[]
        {
            Candidate("low", "The Matrix", 1999, popularity: 100),
            Candidate("high", "The Matrix", 1999, popularity: 500)
        };

        var results = MatchScorer.Score(Hint("The Matrix", 1999, manual: true), candidates);

        Assert.Equal("high", results[0].Candidate.Id);
    }

    [Fact]
    public void Unrelated_title_never_clears_auto_threshold()
    {
        var hint = Hint("Xyzabc", 1985);
        var candidates = new[] { Candidate("bttf", "Back to the Future", 1985, popularity: 100) };

        Assert.Null(MatchScorer.BestMatch(hint, candidates));
    }
}
