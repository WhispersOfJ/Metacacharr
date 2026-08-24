using System.Net;
using System.Net.Http.Json;
using Metacache.Plex.Models;

namespace Metacache.Host.Tests;

public class TvMetadataEndpointTests : ProviderEndpointTestBase
{
    [Fact]
    public async Task Show_metadata_returns_full_plex_object()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-show-15260");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal("tv.plex.agents.custom.metacache.tv", container.Identifier);

        MetadataItem item = Assert.Single(container.Metadata);
        Assert.Equal("tmdb-show-15260", item.RatingKey);
        Assert.Equal("show", item.Type);
        Assert.Equal("Adventure Time", item.Title);
        Assert.Equal(2010, item.Year);
        Assert.Equal("2010-04-05", item.OriginallyAvailableAt);
        Assert.Equal(660_000, item.Duration); // 11 min episode runtime
        Assert.Equal("TV-PG", item.ContentRating);
        Assert.StartsWith("/img/", item.Thumb);
        Assert.StartsWith("/img/", item.Art);

        Assert.Contains(item.GuidItems!, g => g.Id == "tmdb://15260");
        Assert.Contains(item.GuidItems!, g => g.Id == "imdb://tt1305826");
        Assert.Contains(item.GuidItems!, g => g.Id == "tvdb://152831");
        Assert.Contains(item.Genre!, g => g.Tag == "Animation");
        Assert.Contains(item.Network!, n => n.Tag == "Cartoon Network");
        Assert.Contains(item.StudioItems!, s => s.Tag == "Cartoon Network Studios");
        Assert.Contains(item.Role!, r => r.Tag == "Jeremy Shada");
        Assert.Null(item.Children); // includeChildren not requested
        Assert.Equal(4, Upstream.Requests.Count); // show + credits + content ratings + external ids
    }

    [Fact]
    public async Task Show_metadata_includes_children_when_requested()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-show-15260?includeChildren=1");

        MetadataItem item = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer.Metadata[0];
        Assert.Equal(2, item.Children!.Size);
        MetadataItem firstSeason = item.Children.Metadata[0];
        Assert.Equal("tmdb-season-15260-1", firstSeason.RatingKey);
        Assert.Equal("Season 1", firstSeason.Title);
        Assert.Equal(1, firstSeason.Index);
        Assert.Equal("show", firstSeason.ParentType);
        Assert.Equal("Adventure Time", firstSeason.ParentTitle);
        Assert.Equal("tmdb-show-15260", firstSeason.ParentRatingKey);
    }

    [Fact]
    public async Task Show_children_are_paged()
    {
        var request = new HttpRequestMessage(HttpMethod.Get, "/library/metadata/tmdb-show-15260/children");
        request.Headers.Add("X-Plex-Container-Size", "1");

        var response = await Client.SendAsync(request);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;

        Assert.Equal(1, container.Size);
        Assert.Equal(2, container.TotalSize);
        Assert.Equal(0, container.Offset);
        Assert.Equal("tmdb-season-15260-1", container.Metadata[0].RatingKey);

        // Second page via start=2.
        var pageTwo = new HttpRequestMessage(HttpMethod.Get, "/library/metadata/tmdb-show-15260/children?X-Plex-Container-Start=2");
        pageTwo.Headers.Add("X-Plex-Container-Size", "1");
        MetadataContainer second = (await ReadProviderAsync<MetadataContainerResponse>(await Client.SendAsync(pageTwo)))!.MediaContainer;
        Assert.Equal(1, second.Size);
        Assert.Equal(1, second.Offset);
        Assert.Equal("tmdb-season-15260-2", second.Metadata[0].RatingKey);
    }

    [Fact]
    public async Task Season_metadata_has_parent_fields_and_rating()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-season-15260-1");

        MetadataItem item = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer.Metadata[0];
        Assert.Equal("tmdb-season-15260-1", item.RatingKey);
        Assert.Equal("season", item.Type);
        Assert.Equal("Season 1", item.Title);
        Assert.Equal(1, item.Index);
        Assert.Equal("Adventure Time", item.ParentTitle);
        Assert.Equal("show", item.ParentType);
        Assert.Equal("tmdb-show-15260", item.ParentRatingKey);
        Assert.Equal("TV-PG", item.ContentRating);
        Assert.Equal(3, Upstream.Requests.Count); // show + season + content ratings
    }

    [Fact]
    public async Task Season_children_returns_episodes_with_grandparent_fields()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-season-15260-1/children");

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(2, container.Size);
        Assert.Equal(2, container.TotalSize);

        MetadataItem first = container.Metadata[0];
        Assert.Equal("tmdb-episode-15260-1-1", first.RatingKey);
        Assert.Equal("Slumber Party Panic", first.Title);
        Assert.Equal("episode", first.Type);
        Assert.Equal(1, first.Index);
        Assert.Equal(1, first.ParentIndex);
        Assert.Equal("Season 1", first.ParentTitle);
        Assert.Equal("Adventure Time", first.GrandparentTitle);
        Assert.Equal("tmdb-show-15260", first.GrandparentRatingKey);
        Assert.StartsWith("/img/", first.Thumb);
    }

    [Fact]
    public async Task Episode_metadata_returns_full_item()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-episode-15260-1-1");

        MetadataItem item = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer.Metadata[0];
        Assert.Equal("tmdb-episode-15260-1-1", item.RatingKey);
        Assert.Equal("episode", item.Type);
        Assert.Equal("Slumber Party Panic", item.Title);
        Assert.Equal(1, item.ParentIndex);
        Assert.Equal(1, item.Index);
        Assert.Equal("2010-04-05", item.OriginallyAvailableAt);
        Assert.Equal("Adventure Time", item.GrandparentTitle);
        Assert.Contains(item.GuidItems!, g => g.Id == "tmdb://71833");
        Assert.Equal(2, Upstream.Requests.Count); // episode + show
    }

    [Fact]
    public async Task Show_grandchildren_return_all_episodes()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-show-15260/grandchildren");

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(3, container.TotalSize);
        Assert.All(container.Metadata, m => Assert.Equal("episode", m.Type));
        Assert.Equal(3, Upstream.Requests.Count); // show + both seasons
    }

    [Fact]
    public async Task Unknown_show_returns_404()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-show-999999999");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Unknown_season_returns_404()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-season-15260-9");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Unknown_episode_returns_404()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-episode-15260-1-9");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Show_images_endpoint_returns_local_assets()
    {
        var response = await Client.GetAsync("/library/metadata/tmdb-show-15260/images");

        ImageContainer container = (await ReadProviderAsync<ImageContainerResponse>(response))!.MediaContainer;
        Assert.Equal(2, container.Size);
        Assert.All(container.Image, i => Assert.StartsWith("/img/", i.Url));
        Assert.Contains(container.Image, i => i.Type == "coverPoster");
        Assert.Contains(container.Image, i => i.Type == "background");
    }
}
