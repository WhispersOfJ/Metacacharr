using System.Net;
using System.Text.Json;
using Metacache.Core.Cache;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests;

/// <summary>
/// End-to-end tests for the queryable cache index (DESIGN.md §19): /items search over
/// the normalized store and /guid/lookup translation across imdb/tmdb/tvdb, both backed
/// by the real host with the fake TMDB upstream. Items are seeded straight into the
/// factory's in-memory store, so the searches exercise the actual DI + SQL path.
/// </summary>
public class CacheIndexEndpointsTests : ProviderEndpointTestBase
{
    private CacheStore Store => Factory.Services.GetRequiredService<CacheStore>();

    // ---- /items ----

    [Fact]
    public async Task Items_search_filters_by_kind_title_and_guid()
    {
        SeedMovie105();
        SeedMovie165();
        SeedShow15260();

        var all = await GetAsync("/items");
        Assert.Equal(3, Prop(all, "total").GetInt32());

        var movies = await GetAsync("/items?kind=movie");
        Assert.Equal(2, Prop(movies, "total").GetInt32());

        var partTwo = await GetAsync("/items?q=part%20ii");
        JsonElement only = Assert.Single(Prop(partTwo, "items").EnumerateArray());
        Assert.Equal("movie-165", only.GetProperty("id").GetString());
        Assert.Equal("Back to the Future Part II", only.GetProperty("title").GetString());
        Assert.Equal(1989, only.GetProperty("year").GetInt32());

        // Guid filter resolves through the lookup into the tmdb source id.
        var byGuid = await GetAsync("/items?guid=imdb%3A%2F%2Ftt0088763");
        Assert.Equal(1, Prop(byGuid, "total").GetInt32());
        Assert.Equal("movie-105", Assert.Single(Prop(byGuid, "items").EnumerateArray()).GetProperty("id").GetString());
    }

    [Fact]
    public async Task Items_fresh_filter_and_limit()
    {
        SeedItem("movie-1", "movie", "1", "Fresh", 1990, expired: false);
        SeedItem("movie-2", "movie", "2", "Stale", 1991, expired: true);

        var fresh = await GetAsync("/items?fresh=true");
        Assert.Equal("movie-1", Assert.Single(Prop(fresh, "items").EnumerateArray()).GetProperty("id").GetString());

        var paged = await GetAsync("/items?limit=1");
        Assert.Equal(1, Prop(paged, "items").GetArrayLength());
        Assert.Equal(2, Prop(paged, "total").GetInt32());
    }

    [Fact]
    public async Task Items_validates_its_query_parameters()
    {
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/items?kind=clip")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/items?fresh=banana")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/items?limit=0")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/items?limit=abc")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Client.GetAsync("/items?guid=imdb%3A%2F%2Ftt999999")).StatusCode);
    }

    // ---- /guid/lookup ----

    [Fact]
    public async Task Lookup_movie_imdb_resolves_all_equivalents()
    {
        SeedMovie105();

        var doc = await LookupAsync("imdb://tt0088763");

        Assert.Equal("movie", Prop(doc, "kind").GetString());
        Assert.Equal("Back to the Future", Prop(doc, "title").GetString());
        Assert.Equal(1985, Prop(doc, "year").GetInt32());
        Assert.Equal("imdb://tt0088763", Prop(doc, "imdb").GetString());
        Assert.Equal("tmdb://105", Prop(doc, "tmdb").GetString());
        Assert.Equal(JsonValueKind.Null, Prop(doc, "tvdb").ValueKind);
        Assert.Equal("movie-105", Prop(doc, "itemId").GetString());
        Assert.True(Prop(doc, "cached").GetBoolean());
        Assert.Equal(2, Upstream.Requests.Count); // find + movie details
    }

    [Fact]
    public async Task Lookup_show_imdb_and_tvdb_resolve_to_the_same_show()
    {
        var viaImdb = await LookupAsync("imdb://tt1305826");
        Assert.Equal("show", Prop(viaImdb, "kind").GetString());
        Assert.Equal("Adventure Time", Prop(viaImdb, "title").GetString());
        Assert.Equal(2010, Prop(viaImdb, "year").GetInt32());
        Assert.Equal("tmdb://15260", Prop(viaImdb, "tmdb").GetString());
        Assert.Equal("tvdb://152831", Prop(viaImdb, "tvdb").GetString());
        Assert.Equal(JsonValueKind.Null, Prop(viaImdb, "itemId").ValueKind); // not in the index
        Assert.False(Prop(viaImdb, "cached").GetBoolean());

        var viaTvdb = await LookupAsync("tvdb://152831");
        Assert.Equal("tmdb://15260", Prop(viaTvdb, "tmdb").GetString());
        Assert.Equal("imdb://tt1305826", Prop(viaTvdb, "imdb").GetString());
    }

    [Fact]
    public async Task Lookup_accepts_tmdb_rating_key_and_guid_forms()
    {
        Assert.Equal("movie", Prop(await LookupAsync("tmdb-movie-105"), "kind").GetString());
        Assert.Equal("tmdb://105", Prop(await LookupAsync("tmdb://105"), "tmdb").GetString());
        Assert.Equal("show", Prop(await LookupAsync("tmdb://15260"), "kind").GetString());
        Assert.Equal("show", Prop(await LookupAsync("tmdb-season-15260-1"), "kind").GetString()); // season → show level
        Assert.Equal("show", Prop(await LookupAsync("tmdb-episode-15260-1-1"), "kind").GetString());
    }

    [Fact]
    public async Task Lookup_bare_tmdb_id_probes_kind_via_upstream()
    {
        // 165 isn't in the index, so the probe tries /tv/165 (404, cached) then /movie/165.
        var doc = await LookupAsync("165");

        Assert.Equal("movie", Prop(doc, "kind").GetString());
        Assert.Equal("tmdb://165", Prop(doc, "tmdb").GetString());
        Assert.Equal("imdb://tt0096874", Prop(doc, "imdb").GetString());
    }

    [Fact]
    public async Task Lookup_unknown_guid_returns_404()
    {
        var response = await Client.GetAsync("/guid/lookup?guid=imdb%3A%2F%2Ftt999999");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Lookup_missing_guid_returns_400()
    {
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/guid/lookup")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client.GetAsync("/guid/lookup?guid=")).StatusCode);
    }

    [Fact]
    public async Task Repeated_lookups_are_served_from_cache()
    {
        await LookupAsync("imdb://tt0088763");
        int calls = Upstream.Requests.Count;
        Assert.Equal(2, calls); // find + movie details

        await LookupAsync("imdb://tt0088763");
        Assert.Equal(calls, Upstream.Requests.Count); // zero new upstream calls

        await LookupAsync("tvdb://152831");
        await LookupAsync("tvdb://152831");
        Assert.Equal(calls + 3, Upstream.Requests.Count); // find(tvdb) + show + external ids, then cache hits
    }

    [Fact]
    public async Task Indexed_item_is_reported_cached_even_on_a_guid_input()
    {
        SeedMovie105();

        var doc = await LookupAsync("tmdb://105");
        Assert.Equal("movie-105", Prop(doc, "itemId").GetString());
        Assert.True(Prop(doc, "cached").GetBoolean());
    }

    // ---- helpers ----

    private async Task<JsonDocument> LookupAsync(string guid)
    {
        var response = await Client.GetAsync($"/guid/lookup?guid={Uri.EscapeDataString(guid)}");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return JsonDocument.Parse(await response.Content.ReadAsStringAsync());
    }

    private async Task<JsonDocument> GetAsync(string path)
    {
        var response = await Client.GetAsync(path);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return JsonDocument.Parse(await response.Content.ReadAsStringAsync());
    }

    private static JsonElement Prop(JsonDocument doc, string name) => doc.RootElement.GetProperty(name);

    private void SeedMovie105() => SeedItem("movie-105", "movie", "105", "Back to the Future", 1985, expired: false);

    private void SeedMovie165() => SeedItem("movie-165", "movie", "165", "Back to the Future Part II", 1989, expired: false);

    private void SeedShow15260() => SeedItem("show-15260", "show", "15260", "Adventure Time", 2010, expired: false);

    private void SeedItem(string id, string kind, string sourceId, string? title, int? year, bool expired)
    {
        var now = DateTimeOffset.UtcNow;
        Store.PutItem(new CachedItem(id, kind, "tmdb", sourceId, "en-US", "{}",
            now, expired ? now.AddHours(-1) : now.AddHours(1), null, title, year));
    }
}
