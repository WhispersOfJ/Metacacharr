using Metacache.Core.Matching;

namespace Metacache.Host.Tests.Matching;

public class TitleNormalizerTests
{
    [Theory]
    [InlineData("The Matrix", "matrix")]
    [InlineData("A Quiet Place", "quiet place")]
    [InlineData("An American Werewolf in London", "american werewolf in london")]
    [InlineData("Star Wars: Episode IV – A New Hope", "star wars episode 4 a new hope")] // only leading articles are stripped
    [InlineData("Rocky II", "rocky 2")]
    [InlineData("Don\u2019t Breathe", "don t breathe")] // smart apostrophe
    [InlineData("  THE   MATRIX  ", "matrix")]
    [InlineData(null, "")]
    [InlineData("", "")]
    public void Normalize_produces_expected_keys(string? input, string expected)
    {
        Assert.Equal(expected, TitleNormalizer.Normalize(input));
    }

    [Fact]
    public void Similarity_is_one_for_identical_and_article_variants()
    {
        Assert.Equal(1.0, TitleNormalizer.Similarity("The Matrix", "Matrix"));
        Assert.Equal(1.0, TitleNormalizer.Similarity("Back to the Future", "Back to the Future"));
    }

    [Fact]
    public void Similarity_scores_close_sequels_below_exact()
    {
        // "rocky" vs "rocky 2": token Jaccard 0.5, bigram Dice 0.8 → max is 0.8.
        double similarity = TitleNormalizer.Similarity("Rocky", "Rocky II");
        Assert.Equal(0.8, similarity, 6);
        Assert.True(similarity < 1.0);
    }

    [Fact]
    public void Unrelated_titles_stay_far_below_thresholds()
    {
        // Word-level Jaccard is 0; bigram-Dice leaves a small noise floor (~0.14) from
        // coincidental substrings — far below the auto-match (0.6) and manual (0.15) floors.
        double similarity = TitleNormalizer.Similarity("Total Recall", "Back to the Future");
        Assert.True(similarity < 0.2, $"unexpected similarity {similarity}");
    }

    [Fact]
    public void Token_jaccard_ignores_word_order()
    {
        Assert.Equal(0.5, TitleNormalizer.TokenJaccard("back to the future", "back future"), 6);
        Assert.Equal(1.0, TitleNormalizer.TokenJaccard("a b c", "c a b"), 6);
    }
}
