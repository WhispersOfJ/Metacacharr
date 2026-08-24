using Metacache.Plex.Warming;

namespace Metacache.Host.Tests.Warming;

public class PlexPlayParserTests
{
    [Fact]
    public void Movie_play_parses_title_year_and_guid_array()
    {
        var payload = PlexPlayParser.Parse("""
            {
              "event": "media.play",
              "Metadata": {
                "type": "movie",
                "title": "Back to the Future",
                "year": 1985,
                "guid": "plex://movie/5d7768c...",
                "Guid": [ { "id": "imdb://tt0088763", "provider": "imdb" } ]
              }
            }
            """);

        Assert.NotNull(payload);
        Assert.Equal("media.play", payload.Event);
        PlexPlayMetadata meta = payload.Metadata!;
        Assert.Equal("movie", meta.Kind);
        Assert.Equal("Back to the Future", meta.Title);
        Assert.Equal(1985, meta.Year);
        Assert.Equal(["imdb://tt0088763"], meta.Guids);
    }

    [Fact]
    public void Episode_play_parses_show_season_and_episode()
    {
        var payload = PlexPlayParser.Parse("""
            {
              "event": "media.play",
              "Metadata": {
                "type": "episode",
                "title": "Slumber Party Panic",
                "grandparentTitle": "Adventure Time",
                "parentIndex": 1,
                "index": 1,
                "year": 2010,
                "Guid": [ { "id": "tvdb://282648", "provider": "tvdb" } ]
              }
            }
            """);

        PlexPlayMetadata meta = payload!.Metadata!;
        Assert.Equal("episode", meta.Kind);
        Assert.Equal("Slumber Party Panic", meta.Title);
        Assert.Equal("Adventure Time", meta.ShowTitle);
        Assert.Equal(1, meta.Season);
        Assert.Equal(1, meta.Episode);
        Assert.Equal(["tvdb://282648"], meta.Guids);
    }

    [Fact]
    public void Legacy_guid_field_is_used_when_the_guid_array_is_absent()
    {
        var payload = PlexPlayParser.Parse("""
            { "event": "media.play", "Metadata": { "type": "movie", "guid": "tmdb://105" } }
            """);

        Assert.Equal(["tmdb://105"], payload!.Metadata!.Guids);
    }

    [Fact]
    public void Non_movie_or_episode_metadata_is_ignored()
    {
        var payload = PlexPlayParser.Parse("""
            { "event": "media.play", "Metadata": { "type": "track", "title": "Song" } }
            """);

        Assert.Equal("media.play", payload!.Event);
        Assert.Null(payload.Metadata);
    }

    [Fact]
    public void Non_play_events_parse_without_metadata_requirements()
    {
        var payload = PlexPlayParser.Parse("""
            { "event": "media.pause", "Metadata": { "type": "movie" } }
            """);

        Assert.Equal("media.pause", payload!.Event);
        Assert.NotNull(payload.Metadata);
    }

    [Fact]
    public void Invalid_json_returns_null()
    {
        Assert.Null(PlexPlayParser.Parse("not json"));
        Assert.Null(PlexPlayParser.Parse(""));
    }

    [Fact]
    public void Missing_event_returns_null()
    {
        Assert.Null(PlexPlayParser.Parse("""{ "Metadata": { "type": "movie" } }"""));
    }
}
