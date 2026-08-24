using Metacache.Core.Providers;
using Metacache.Plex.Mappers;

namespace Metacache.Host.Tests;

/// <summary>
/// Regression tests for the country-aware rating selection: the live M3 warm against a
/// real TMDB show whose content ratings had no US entry crashed because FirstOrDefault
/// on a value-tuple list returns the default tuple (null, null) — never null — and the
/// code then called .All on the null Values list.
/// </summary>
public class PeopleMapperTests
{
    [Fact]
    public void TvContentRating_without_the_requested_country_falls_back_instead_of_throwing()
    {
        var ratings = new TmdbContentRatingsResponse(
            [new TmdbContentRating("DE", "FSK 6"), new TmdbContentRating("GB", "15")]);

        string? result = PeopleMapper.TvContentRating(ratings, country: null); // defaults to US

        Assert.Equal("de/FSK 6", result); // no US entry → first non-empty fallback
    }

    [Fact]
    public void TvContentRating_with_the_requested_country_returns_it_bare()
    {
        var ratings = new TmdbContentRatingsResponse(
            [new TmdbContentRating("DE", "FSK 6"), new TmdbContentRating("US", "TV-PG")]);

        Assert.Equal("TV-PG", PeopleMapper.TvContentRating(ratings, country: "US"));
    }

    [Fact]
    public void TvContentRating_with_empty_results_returns_null()
    {
        Assert.Null(PeopleMapper.TvContentRating(new TmdbContentRatingsResponse([]), country: null));
        Assert.Null(PeopleMapper.TvContentRating(null, country: null));
    }

    [Fact]
    public void MovieCertification_without_the_requested_country_falls_back_instead_of_throwing()
    {
        var releaseDates = new TmdbReleaseDatesResponse(
            [new TmdbReleaseDateResult("DE", [new TmdbReleaseDate("FSK 12")])]);

        string? result = PeopleMapper.MovieCertification(releaseDates, country: null);

        Assert.Equal("de/FSK 12", result);
    }

    [Fact]
    public void MovieCertification_with_us_returns_it_bare()
    {
        var releaseDates = new TmdbReleaseDatesResponse(
            [new TmdbReleaseDateResult("US", [new TmdbReleaseDate("PG")])]);

        Assert.Equal("PG", PeopleMapper.MovieCertification(releaseDates, country: null));
    }
}
