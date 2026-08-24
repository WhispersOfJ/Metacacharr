using System.Net;
using System.Net.Http.Json;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;
using Metacache.Plex.Models;

namespace Metacache.Host.Tests;

public class TvMatchEndpointTests : ProviderEndpointTestBase
{
    private const string TvIdentifier = "tv.plex.agents.custom.metacache.tv";

    [Fact]
    public async Task Show_auto_match_returns_best_show()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":2,"title":"Adventure Time"}"""));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(TvIdentifier, container.Identifier);

        MetadataItem item = Assert.Single(container.Metadata);
        Assert.Equal("tmdb-show-15260", item.RatingKey);
        Assert.Equal($"{TvIdentifier}://show/tmdb-show-15260", item.Guid);
        Assert.Equal("show", item.Type);
        Assert.Equal("Adventure Time", item.Title);
        Assert.Equal(2010, item.Year);
        Assert.Equal(2, Upstream.Requests.Count); // search + show
    }

    [Fact]
    public async Task Show_match_by_external_guid_pins_the_exact_show()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":2,"guid":"imdb://tt1305826"}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal("tmdb-show-15260", Assert.Single(container.Metadata).RatingKey);
        Assert.Equal(3, Upstream.Requests.Count); // find + show + external ids
    }

    [Fact]
    public async Task Season_match_uses_the_index_as_a_structure_gate()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":3,"parentTitle":"Adventure Time","index":1}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal("tmdb-season-15260-1", Assert.Single(container.Metadata).RatingKey);
    }

    [Fact]
    public async Task Season_match_with_wrong_index_returns_empty()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":3,"parentTitle":"Adventure Time","index":9}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(0, container.Size);
        Assert.Empty(container.Metadata);
    }

    [Fact]
    public async Task Season_match_returns_children_when_requested()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":3,"parentTitle":"Adventure Time","index":1,"includeChildren":1}"""));

        MetadataItem item = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer.Metadata[0];
        Assert.Equal("tmdb-season-15260-1", item.RatingKey);
        Assert.Equal(2, item.Children!.Size);
        Assert.Equal("tmdb-episode-15260-1-1", item.Children.Metadata[0].RatingKey);
    }

    [Fact]
    public async Task Episode_match_by_season_and_episode_index()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":4,"grandparentTitle":"Adventure Time","parentIndex":1,"index":1}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        MetadataItem item = Assert.Single(container.Metadata);
        Assert.Equal("tmdb-episode-15260-1-1", item.RatingKey);
        Assert.Equal("episode", item.Type);
        Assert.Equal(1, item.ParentIndex);
        Assert.Equal(1, item.Index);
        Assert.Equal(3, Upstream.Requests.Count); // search + show + one season
    }

    [Fact]
    public async Task Episode_match_by_air_date()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":4,"grandparentTitle":"Adventure Time","date":"2010-04-05"}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal("tmdb-episode-15260-1-1", Assert.Single(container.Metadata).RatingKey);
        Assert.Equal(4, Upstream.Requests.Count); // search + show + both seasons
    }

    [Fact]
    public async Task Episode_match_for_the_wrong_show_returns_empty()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":4,"grandparentTitle":"Breaking Bad","parentIndex":1,"index":1}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(0, container.Size);
    }

    [Fact]
    public async Task Manual_episode_match_returns_a_ranked_list_across_seasons()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":4,"grandparentTitle":"Adventure Time","manual":1}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(3, container.Size); // 2 episodes of S1 + 1 of S2
        Assert.Equal("tmdb-episode-15260-1-1", container.Metadata[0].RatingKey);
    }

    [Fact]
    public async Task Show_match_can_include_season_children()
    {
        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":2,"title":"Adventure Time","includeChildren":1}"""));

        MetadataItem item = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer.Metadata[0];
        Assert.Equal(2, item.Children!.Size);
        Assert.Equal("tmdb-season-15260-1", item.Children.Metadata[0].RatingKey);
    }

    [Fact]
    public async Task Episode_match_augments_from_tvdb_when_tmdb_has_no_episode_data()
    {
        // TMDB has the show but its season payloads carry zero episodes — the scorer must
        // fall back to TVDB (via the show's tvdb external id) so index matching still works.
        Func<UpstreamRequest, UpstreamResponse> baseHandler = Upstream.Handler;
        Upstream.Handler = request =>
        {
            string path = request.Url.AbsolutePath;
            if (path.EndsWith("/tv/15260/season/1", StringComparison.Ordinal)
                || path.EndsWith("/tv/15260/season/2", StringComparison.Ordinal))
                return Json(TmdbTestData.SeasonNoEpisodesJson);
            return baseHandler(request);
        };

        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":4,"grandparentTitle":"Adventure Time","parentIndex":1,"index":1}"""));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        MetadataItem item = Assert.Single(container.Metadata);
        Assert.Equal("tmdb-episode-15260-1-1", item.RatingKey);
        Assert.Equal("Slumber Party Panic", item.Title); // from TVDB, not TMDB
        Assert.Equal("2010-04-05", item.OriginallyAvailableAt);
        Assert.Equal(1, item.ParentIndex);
        Assert.Equal(1, item.Index);
        Assert.Equal("tvdb://7100001", Assert.Single(item.GuidItems!).Id); // honest source, not a tmdb-prefixed TVDB id
    }

    private static UpstreamResponse Json(string body) =>
        new(200, TestBytes.Of(body), "application/json", null, null, null);
}
