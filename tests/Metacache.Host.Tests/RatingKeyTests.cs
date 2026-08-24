using Metacache.Plex;

namespace Metacache.Host.Tests;

public class RatingKeyTests
{
    [Fact]
    public void Movie_key_round_trips()
    {
        var key = RatingKey.Movie("tmdb", "19934");

        Assert.Equal("tmdb-movie-19934", key);
        Assert.True(RatingKey.TryParse(key, out var parsed));
        Assert.Equal(("tmdb", "movie", "19934"), (parsed.Source, parsed.Kind, parsed.Id));
        Assert.Empty(parsed.Indices);
    }

    [Fact]
    public void Episode_key_carries_season_and_episode_indices()
    {
        var key = RatingKey.Episode("tmdb", "4020", 1, 4);

        Assert.Equal("tmdb-episode-4020-1-4", key);
        Assert.True(RatingKey.TryParse(key, out var parsed));
        Assert.Equal("4020", parsed.Id);
        Assert.Equal([1, 4], parsed.Indices);
    }

    [Fact]
    public void Tvdb_show_key_parses()
    {
        var key = RatingKey.Show("tvdb", "78874");

        Assert.True(RatingKey.TryParse(key, out var parsed));
        Assert.Equal(("tvdb", "show", "78874"), (parsed.Source, parsed.Kind, parsed.Id));
    }

    [Theory]
    [InlineData("")]
    [InlineData("tmdb-movie")]                 // missing id
    [InlineData("tmdb-season-4020")]           // missing index
    [InlineData("tmdb-season-4020-1-2")]       // too many indices
    [InlineData("tmdb-episode-4020-1")]        // missing episode index
    [InlineData("tmdb-movie-19934-extra")]     // unexpected index on a movie
    [InlineData("tmdb-unknown-123")]           // unknown kind
    [InlineData("bad/key-with-slash-1")]       // forbidden characters
    public void Invalid_keys_are_rejected(string key)
    {
        Assert.False(RatingKey.TryParse(key, out _));
        Assert.False(RatingKey.IsValid(key));
    }

    [Fact]
    public void Guid_uses_plex_format()
    {
        var ratingKey = RatingKey.Movie("tmdb", "19934");

        var guid = PlexGuid.Format("tv.plex.agents.custom.metacache.movie", "movie", ratingKey);

        Assert.Equal("tv.plex.agents.custom.metacache.movie://movie/tmdb-movie-19934", guid);
    }
}
