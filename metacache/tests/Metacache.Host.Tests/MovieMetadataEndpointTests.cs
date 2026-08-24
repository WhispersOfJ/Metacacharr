using System.Net;
using System.Net.Http.Json;
using Metacache.Plex.Models;

namespace Metacache.Host.Tests;

public class MovieMetadataEndpointTests : ProviderEndpointTestBase
{
    [Fact]
    public async Task Metadata_returns_full_plex_object_with_rewritten_images()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-movie-105");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(1, container.Size);
        Assert.Equal("tv.plex.agents.custom.metacache.movie", container.Identifier);

        MetadataItem item = Assert.Single(container.Metadata);
        Assert.Equal("tmdb-movie-105", item.RatingKey);
        Assert.Equal("/library/metadata/tmdb-movie-105", item.Key);
        Assert.Equal("tv.plex.agents.custom.metacache.movie://movie/tmdb-movie-105", item.Guid);
        Assert.Equal("movie", item.Type);
        Assert.Equal("Back to the Future", item.Title);
        Assert.Equal(1985, item.Year);
        Assert.Equal("1985-07-03", item.OriginallyAvailableAt);
        Assert.Equal(6_960_000, item.Duration);
        Assert.Equal("Marty McFly travels back in time.", item.Summary);
        Assert.StartsWith("/img/", item.Thumb);
        Assert.StartsWith("/img/", item.Art);

        Assert.Contains(item.GuidItems!, g => g.Id == "tmdb://105");
        Assert.Contains(item.GuidItems!, g => g.Id == "imdb://tt0088763");
        Assert.Equal(["Adventure", "Comedy"], item.Genre!.Select(g => g.Tag));
        Assert.Contains(item.Country!, c => c.Tag == "United States of America");
        Assert.Contains(item.StudioItems!, s => s.Tag == "Universal Pictures");
        Assert.Equal("Universal Pictures", item.Studio);

        Assert.Equal(2, item.Image!.Count);
        Assert.Equal("coverPoster", item.Image[0].Type);
        Assert.Equal("background", item.Image[1].Type);
        Assert.StartsWith("/img/", item.Image[0].Url);

        RatingItem rating = Assert.Single(item.Rating!);
        Assert.Equal("themoviedb://image.rating", rating.Image);
        Assert.Equal("audience", rating.Type);
        Assert.Equal(8.3, rating.Value);

        Assert.Equal("PG", item.ContentRating); // US default, bare
        Assert.Contains(item.Role!, r => r is { Tag: "Michael J. Fox", Role: "Marty McFly" });
        Assert.Contains(item.Director!, d => d.Tag == "Robert Zemeckis");
        Assert.Contains(item.Writer!, w => w.Tag == "Bob Gale");
        Assert.Contains(item.Producer!, p => p.Tag == "Neil Canton");
        Assert.StartsWith("/img/", item.Role![0].Thumb); // person photo rewritten too
    }

    [Fact]
    public async Task Content_rating_follows_the_requested_country()
    {
        var request = new HttpRequestMessage(HttpMethod.Get, "/library/metadata/tmdb-movie-105");
        request.Headers.Add("X-Plex-Country", "DE");

        var response = await Client.SendAsync(request);
        MetadataItem item = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer.Metadata[0];

        Assert.Equal("de/FSK 12", item.ContentRating); // non-US ratings are country-prefixed
    }

    [Fact]
    public async Task Rewritten_image_urls_are_fetchable_on_first_request()
    {
        var metadata = await Client.GetAsync("/library/metadata/tmdb-movie-105");
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(metadata))!.MediaContainer;
        string imgPath = container.Metadata[0].Thumb!;
        Assert.StartsWith("/img/", imgPath);

        // The provider registered the URL when it rewrote it, so the very first
        // /img request resolves (fetches + stores) instead of 404ing.
        var image = await Client.GetAsync(imgPath);

        Assert.Equal(HttpStatusCode.OK, image.StatusCode);
        Assert.Equal("image/jpeg", image.Content.Headers.ContentType!.MediaType);
        Assert.Equal("fake-jpeg-bytes", await image.Content.ReadAsStringAsync());
        Assert.Equal(4, Upstream.Requests.Count); // details + credits + release dates + one image fetch
    }

    [Fact]
    public async Task Metadata_is_served_from_cache_on_refresh()
    {
        await Client.GetAsync("/library/metadata/tmdb-movie-105");
        var response = await Client.GetAsync("/library/metadata/tmdb-movie-105");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(3, Upstream.Requests.Count); // details + credits + release dates, fetched once
    }

    [Fact]
    public async Task Unknown_movie_returns_404()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-movie-999999999");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Non_tmdb_source_returns_404_without_hitting_upstream()
    {
        var response = await Client.GetAsync("/library/metadata/tvdb-show-78874");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Empty(Upstream.Requests);
    }

    [Fact]
    public async Task Malformed_key_returns_404()
    {
        var response = await Client.GetAsync("/library/metadata/not-a-rating-key");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Images_endpoint_returns_local_image_assets()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-movie-105/images");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        ImageContainer container = (await ReadProviderAsync<ImageContainerResponse>(response))!.MediaContainer;

        Assert.Equal(2, container.Size);
        Assert.Equal(2, container.TotalSize);
        Assert.All(container.Image, i => Assert.StartsWith("/img/", i.Url));
        Assert.Contains(container.Image, i => i.Type == "coverPoster");
        Assert.Contains(container.Image, i => i.Type == "background");
    }

    [Fact]
    public async Task Images_404_for_unknown_movie()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-movie-999999999/images");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Metadata_uses_exact_plex_json_casing()
    {
        string raw = await Client.GetStringAsync("/library/metadata/tmdb-movie-105");

        Assert.Contains("\"MediaContainer\"", raw);
        Assert.Contains("\"Metadata\"", raw);
        Assert.Contains("\"Image\"", raw);
        Assert.Contains("\"Guid\"", raw);
        Assert.Contains("\"Genre\"", raw);
        Assert.Contains("\"ratingKey\"", raw);
        Assert.Contains("\"originallyAvailableAt\"", raw);
        Assert.Contains("\"themoviedb://image.rating\"", raw);
    }
}
