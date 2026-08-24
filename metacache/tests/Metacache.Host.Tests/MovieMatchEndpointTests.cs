using System.Net;
using System.Net.Http.Json;
using Metacache.Plex.Models;

namespace Metacache.Host.Tests;

public class MovieMatchEndpointTests : ProviderEndpointTestBase
{
    private const string MovieIdentifier = "tv.plex.agents.custom.metacache.movie";

    [Fact]
    public async Task Auto_match_returns_best_candidate_with_two_upstream_calls()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Back to the Future","year":1985}"""));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;

        Assert.Equal(1, container.Size);
        Assert.Equal(MovieIdentifier, container.Identifier);

        MetadataItem item = Assert.Single(container.Metadata);
        Assert.Equal("tmdb-movie-105", item.RatingKey);
        Assert.Equal($"{MovieIdentifier}://movie/tmdb-movie-105", item.Guid);
        Assert.Equal("movie", item.Type);
        Assert.Equal("Back to the Future", item.Title);
        Assert.Equal(1985, item.Year);
        Assert.StartsWith("/img/", item.Thumb);
        Assert.Equal(2, Upstream.Requests.Count); // search + one details enrichment
    }

    [Fact]
    public async Task Repeated_match_serves_entirely_from_cache()
    {
        string body = """{"type":1,"title":"Back to the Future","year":1985}""";
        await Client.PostAsync("/library/metadata/matches", JsonBody(body));
        var response = await Client.PostAsync("/library/metadata/matches", JsonBody(body));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(2, Upstream.Requests.Count); // no new upstream calls on refresh
    }

    [Fact]
    public async Task Manual_match_returns_a_ranked_list()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Back to the Future","manual":1}"""));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;

        Assert.Equal(2, container.Size);
        Assert.Equal("tmdb-movie-105", container.Metadata[0].RatingKey); // best first
        Assert.Equal("tmdb-movie-165", container.Metadata[1].RatingKey);
    }

    [Fact]
    public async Task Guid_pinning_returns_the_exact_movie()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"guid":"imdb://tt0088763"}"""));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;

        Assert.Equal(1, container.Size);
        Assert.Equal("tmdb-movie-105", Assert.Single(container.Metadata).RatingKey);
        Assert.Equal(2, Upstream.Requests.Count); // find + details
    }

    [Fact]
    public async Task Unknown_guid_returns_an_empty_container()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"guid":"imdb://tt999999"}"""));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(0, container.Size);
        Assert.Empty(container.Metadata);
    }

    [Fact]
    public async Task Adult_results_are_filtered_unless_requested()
    {
        var filtered = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Explicit"}"""));
        Assert.Equal(0, (await ReadProviderAsync<MetadataContainerResponse>(filtered))!.MediaContainer.Size);

        var included = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Explicit","includeAdult":1}"""));
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(included))!.MediaContainer;
        Assert.Equal("tmdb-movie-999", Assert.Single(container.Metadata).RatingKey);
    }

    [Fact]
    public async Task Missing_type_returns_400()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"title":"Back to the Future"}"""));

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task Unknown_type_returns_400()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":9,"title":"x"}"""));

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task Language_header_flows_to_upstream()
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/library/metadata/matches")
        {
            Content = JsonBody("""{"type":1,"title":"Back to the Future"}""")
        };
        request.Headers.Add("X-Plex-Language", "de-DE");

        await Client.SendAsync(request);

        Assert.Contains("language=de-DE",
            Upstream.Requests.Single(r => r.Url.AbsolutePath.EndsWith("/search/movie")).Url.Query);
    }
}
