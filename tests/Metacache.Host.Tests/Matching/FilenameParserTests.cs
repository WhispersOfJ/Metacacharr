using Metacache.Core.Matching;

namespace Metacache.Host.Tests.Matching;

public class FilenameParserTests
{
    private static void AssertParsed(string path, int? expectedYear, params string[] expectedTokens)
    {
        ParsedFilename parsed = FilenameParser.Parse(path);
        Assert.Equal(expectedYear, parsed.Year);
        Assert.Equal(
            expectedTokens.OrderBy(t => t, StringComparer.Ordinal),
            parsed.Tokens.OrderBy(t => t, StringComparer.Ordinal));
    }

    [Fact]
    public void Extracts_year_and_title_tokens_from_folder_and_file()
    {
        AssertParsed(
            "Movies/Back to the Future (1985)/Back.to.the.Future.1985.1080p.BluRay.mkv",
            1985, "back", "to", "the", "future");
    }

    [Fact]
    public void Strips_release_tags_and_parens()
    {
        AssertParsed("The Matrix (1999).mp4", 1999, "matrix");
        AssertParsed("Movies/Inception (2010) 1080p.mkv", 2010, "inception");
        AssertParsed("Movies/Tenet.2020.2160p.WEBDL.x265.mkv", 2020, "tenet");
    }

    [Fact]
    public void Missing_year_yields_null_year()
    {
        AssertParsed("Movies/some-folder/WithoutYear.mkv", null, "withoutyear"); // only the file stem is parsed
    }

    [Fact]
    public void Extracts_season_and_episode_from_sxxeyy()
    {
        ParsedFilename parsed = FilenameParser.Parse("Adventure.Time.S01E05.mkv");
        Assert.Equal(1, parsed.Season);
        Assert.Equal(5, parsed.Episode);
        Assert.Equal(["adventure", "time"], parsed.Tokens.OrderBy(t => t, StringComparer.Ordinal));
    }

    [Fact]
    public void Extracts_season_from_season_n_when_no_episode_number()
    {
        ParsedFilename parsed = FilenameParser.Parse("Adventure Time Season 2.mkv");
        Assert.Equal(2, parsed.Season);
        Assert.Null(parsed.Episode);
    }

    [Fact]
    public void Empty_path_yields_empty_result()
    {
        AssertParsed("", null);
        AssertParsed(null!, null);
    }
}
