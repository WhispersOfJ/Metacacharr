using System.Net;
using System.Net.Http.Json;
using Metacache.Core.Cache;
using Metacache.Plex.Models;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests;

/// <summary>
/// End-to-end tests for the library browse surface (DESIGN.md §21): /library/search
/// and /library/recentlyAdded answered entirely from the warmed index with
/// Plex-shaped containers and sized-variant thumbs.
/// </summary>
public class LibraryBrowseEndpointsTests : ProviderEndpointTestBase
{
    private const string MovieIdentifier = "tv.plex.agents.custom.metacache.movie";
    private const string GenericIdentifier = "tv.plex.agents.custom.metacache";

    private CacheStore Store => Factory.Services.GetRequiredService<CacheStore>();

    [Fact]
    public async Task Search_returns_only_movies_and_shows_with_plex_shapes()
    {
        SeedAll();

        var response = await Client.GetAsync("/library/search");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;

        Assert.Equal(GenericIdentifier, container.Identifier);
        Assert.Equal(2, container.Size); // season + episode rows are /items territory
        Assert.Equal(2, container.TotalSize);

        MetadataItem movie = container.Metadata.First(m => m.RatingKey == "tmdb-movie-105");
        Assert.Equal("movie", movie.Type);
        Assert.Equal($"{MovieIdentifier}://movie/tmdb-movie-105", movie.Guid);
        Assert.Equal("Back to the Future", movie.Title);
        Assert.Equal(1985, movie.Year);
        Assert.EndsWith("?width=185", movie.Thumb); // sized variant for the list view
    }

    [Fact]
    public async Task Search_filters_by_title_kind_and_year()
    {
        SeedAll();

        var byTitle = await GetContainerAsync("/library/search?title=future");
        Assert.Equal(1, byTitle.Size);
        Assert.Equal("tmdb-movie-105", Assert.Single(byTitle.Metadata).RatingKey);

        var byKind = await GetContainerAsync("/library/search?kind=show");
        Assert.Equal(MovieIdentifier.Replace("movie", "tv"), byKind.Identifier);
        Assert.Equal("tmdb-show-15260", Assert.Single(byKind.Metadata).RatingKey);

        var byYear = await GetContainerAsync("/library/search?year=1985");
        Assert.Equal("tmdb-movie-105", Assert.Single(byYear.Metadata).RatingKey);
    }

    [Fact]
    public async Task Search_pages_with_plex_headers()
    {
        SeedAll();

        var request = new HttpRequestMessage(HttpMethod.Get, "/library/search");
        request.Headers.Add("X-Plex-Container-Size", "1");
        request.Headers.Add("X-Plex-Container-Start", "2");
        var response = await Client.SendAsync(request);

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(1, container.Size);
        Assert.Equal(2, container.TotalSize);
        Assert.Equal(1, container.Offset); // start 2 → 0-based offset 1
        Assert.Equal("tmdb-movie-105", Assert.Single(container.Metadata).RatingKey); // title-sorted: Adventure Time, then Back to the Future
    }

    [Fact]
    public async Task Recently_added_lists_most_recent_first()
    {
        var now = DateTimeOffset.UtcNow;
        Store.PutItem(Item("movie-105", "movie", "105", "Back to the Future", 1985, fetchedAt: now.AddDays(-2)));
        Store.PutItem(Item("show-15260", "show", "15260", "Adventure Time", 2010, fetchedAt: now));

        MetadataContainer container = await GetContainerAsync("/library/recentlyAdded");

        Assert.Equal(2, container.TotalSize);
        Assert.Equal("tmdb-show-15260", container.Metadata[0].RatingKey); // newest first
        Assert.Equal("tmdb-movie-105", container.Metadata[1].RatingKey);
    }

    [Fact]
    public async Task Browse_validates_its_parameters()
    {
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/library/search?kind=season")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/library/search?year=abc")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/library/search?year=0")).StatusCode);
    }

    // ---- helpers ----

    private void SeedAll()
    {
        var now = DateTimeOffset.UtcNow;
        Store.PutItem(Item("movie-105", "movie", "105", "Back to the Future", 1985, now));
        Store.PutItem(Item("show-15260", "show", "15260", "Adventure Time", 2010, now));
        Store.PutItem(Item("season-15260-3624", "season", "3624", "Adventure Time", 2010, now));
        Store.PutItem(Item("episode-15260-71833", "episode", "71833", "Adventure Time", 2010, now));
    }

    private async Task<MetadataContainer> GetContainerAsync(string path)
    {
        var response = await Client.GetAsync(path);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
    }

    private static CachedItem Item(string id, string kind, string sourceId, string? title, int? year, DateTimeOffset fetchedAt) =>
        new(id, kind, "tmdb", sourceId, "en-US", "{}", fetchedAt, fetchedAt.AddDays(1), null, title, year, "/img/abc");
}
