using System.Net;
using System.Net.Http.Json;
using Metacache.Core.Matching;
using Metacache.Plex.Models;

namespace Metacache.Host.Tests;

/// <summary>
/// End-to-end tests for the manual-match-pin feature (§15.10): the /admin/overrides
/// and /admin/unmatched surfaces, and the match endpoint's consult-before-search and
/// capture-on-failure behavior.
/// </summary>
public class MatchOverrideEndpointsTests : ProviderEndpointTestBase
{
    private const string MovieKey = "movie:back to the future:1985";

    // ---- admin surface: overrides CRUD ----

    [Fact]
    public async Task Admin_override_roundtrips_through_the_api()
    {
        var created = await Client.PostAsync("/admin/overrides",
            JsonBody($$"""{"key":"{{MovieKey}}","kind":"movie","target":"tmdb-movie-165","notes":"wrong year in plex"}"""));
        Assert.Equal(HttpStatusCode.OK, created.StatusCode);

        MatchOverride read = (await ReadProviderAsync<MatchOverride>(created))!;
        Assert.Equal(MovieKey, read.Key);
        Assert.Equal("movie", read.Kind);
        Assert.Equal("tmdb-movie-165", read.Target);
        Assert.Equal("wrong year in plex", read.Notes);

        var list = await Client.GetAsync("/admin/overrides");
        Assert.Single((await ReadProviderAsync<MatchOverride[]>(list))!);

        var deleted = await Client.DeleteAsync($"/admin/overrides/{MovieKey}");
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);

        var after = await Client.GetAsync("/admin/overrides");
        Assert.Empty((await ReadProviderAsync<MatchOverride[]>(after))!);
    }

    [Fact]
    public async Task Admin_override_validates_its_input()
    {
        // Missing key/target.
        var missing = await Client.PostAsync("/admin/overrides",
            JsonBody("""{"kind":"movie","target":"tmdb-movie-105"}"""));
        Assert.Equal(HttpStatusCode.BadRequest, missing.StatusCode);

        // Unknown kind.
        var badKind = await Client.PostAsync("/admin/overrides",
            JsonBody("""{"key":"k1","kind":"clip","target":"tmdb-movie-105"}"""));
        Assert.Equal(HttpStatusCode.BadRequest, badKind.StatusCode);

        // Non-tmdb target.
        var badTarget = await Client.PostAsync("/admin/overrides",
            JsonBody("""{"key":"k1","kind":"movie","target":"imdb://tt0088763"}"""));
        Assert.Equal(HttpStatusCode.BadRequest, badTarget.StatusCode);

        // Kind/target mismatch.
        var mismatch = await Client.PostAsync("/admin/overrides",
            JsonBody("""{"key":"k1","kind":"show","target":"tmdb-movie-105"}"""));
        Assert.Equal(HttpStatusCode.BadRequest, mismatch.StatusCode);

        // Malformed JSON.
        var malformed = await Client.PostAsync("/admin/overrides", JsonBody("{not json"));
        Assert.Equal(HttpStatusCode.BadRequest, malformed.StatusCode);
    }

    [Fact]
    public async Task Deleting_an_unknown_override_returns_404()
    {
        var response = await Client.DeleteAsync($"/admin/overrides/{MovieKey}");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    // ---- match endpoint: consult-before-search ----

    [Fact]
    public async Task Pinned_override_wins_over_search_in_auto_mode()
    {
        await Client.PostAsync("/admin/overrides",
            JsonBody($$"""{"key":"{{MovieKey}}","kind":"movie","target":"tmdb-movie-165"}"""));

        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Back to the Future","year":1985}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal("tmdb-movie-165", Assert.Single(container.Metadata).RatingKey);
        Assert.Single(Upstream.Requests); // details enrichment only — no search
        Assert.All(Upstream.Requests, r => Assert.EndsWith("/movie/165", r.Url.AbsolutePath));

    }

    [Fact]
    public async Task Pinned_override_leads_the_manual_fix_match_list()
    {
        await Client.PostAsync("/admin/overrides",
            JsonBody($$"""{"key":"{{MovieKey}}","kind":"movie","target":"tmdb-movie-165"}"""));

        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Back to the Future","year":1985,"manual":1}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal(2, container.Size);
        Assert.Equal("tmdb-movie-165", container.Metadata[0].RatingKey); // pin first
        Assert.Equal("tmdb-movie-105", container.Metadata[1].RatingKey); // ranked after, deduped
    }

    [Fact]
    public async Task Tv_show_pin_resolves_through_the_tv_provider()
    {
        await Client.PostAsync("/admin/overrides",
            JsonBody("""{"key":"show:adventure time:","kind":"show","target":"tmdb-show-15260"}"""));

        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":2,"title":"Adventure Time"}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal("tmdb-show-15260", Assert.Single(container.Metadata).RatingKey);
        Assert.Single(Upstream.Requests); // show details only — no search
    }

    [Fact]
    public async Task A_broken_pin_falls_back_to_normal_matching()
    {
        await Client.PostAsync("/admin/overrides",
            JsonBody($$"""{"key":"{{MovieKey}}","kind":"movie","target":"tmdb-movie-999999999"}"""));

        var response = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Back to the Future","year":1985}"""));

        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(response))!.MediaContainer;
        Assert.Equal("tmdb-movie-105", Assert.Single(container.Metadata).RatingKey); // normal search path
    }

    // ---- unmatched capture + pin loop ----

    [Fact]
    public async Task Failed_auto_match_is_captured_then_pinnable_and_the_pin_fires()
    {
        // "Explicit" is adult-filtered in auto mode → zero candidates → captured.
        var failed = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Explicit"}"""));
        Assert.Equal(0, (await ReadProviderAsync<MetadataContainerResponse>(failed))!.MediaContainer.Size);

        var unmatched = await Client.GetAsync("/admin/unmatched");
        UnmatchedEntry entry = Assert.Single((await ReadProviderAsync<UnmatchedEntry[]>(unmatched))!);
        Assert.Equal("movie:explicit:", entry.Key);
        Assert.Equal("movie", entry.Kind);
        Assert.Equal("Explicit", entry.Title);
        Assert.Equal(1, entry.Count);

        // Pin it: creates the override and drops the unmatched entry.
        var pinned = await Client.PostAsync("/admin/unmatched/movie:explicit:/pin",
            JsonBody("""{"target":"tmdb-movie-105","notes":"the explicit one"}"""));
        Assert.Equal(HttpStatusCode.OK, pinned.StatusCode);

        var afterPin = await Client.GetAsync("/admin/unmatched");
        Assert.Empty((await ReadProviderAsync<UnmatchedEntry[]>(afterPin))!);

        var overrides = await Client.GetAsync("/admin/overrides");
        MatchOverride overrideRead = Assert.Single((await ReadProviderAsync<MatchOverride[]>(overrides))!);
        Assert.Equal("movie:explicit:", overrideRead.Key);
        Assert.Equal("tmdb-movie-105", overrideRead.Target);

        // The pin now fires on a plain refresh — no search, adult filter bypassed.
        var refreshed = await Client.PostAsync("/library/metadata/matches",
            JsonBody("""{"type":1,"title":"Explicit"}"""));
        MetadataContainer container = (await ReadProviderAsync<MetadataContainerResponse>(refreshed))!.MediaContainer;
        Assert.Equal("tmdb-movie-105", Assert.Single(container.Metadata).RatingKey);
        Assert.Single(Upstream.Requests, r => r.Url.AbsolutePath.EndsWith("/movie/105"));
    }

    [Fact]
    public async Task Repeated_failures_bump_the_unmatched_count()
    {
        await Client.PostAsync("/library/metadata/matches", JsonBody("""{"type":1,"title":"Explicit"}"""));
        await Client.PostAsync("/library/metadata/matches", JsonBody("""{"type":1,"title":"Explicit"}"""));

        var unmatched = await Client.GetAsync("/admin/unmatched");
        UnmatchedEntry entry = Assert.Single((await ReadProviderAsync<UnmatchedEntry[]>(unmatched))!);
        Assert.Equal(2, entry.Count);
    }

    [Fact]
    public async Task Pinning_an_unknown_unmatched_key_returns_404_and_clear_empties_the_list()
    {
        var missing = await Client.PostAsync("/admin/unmatched/nope/pin", JsonBody("""{"target":"tmdb-movie-105"}"""));
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);

        await Client.PostAsync("/library/metadata/matches", JsonBody("""{"type":1,"title":"Explicit"}"""));
        var cleared = await Client.DeleteAsync("/admin/unmatched");
        Assert.Equal(HttpStatusCode.OK, cleared.StatusCode);
        Assert.Equal(1, (await ReadProviderAsync<RemovedResponse>(cleared))!.Removed);

        var unmatched = await Client.GetAsync("/admin/unmatched");
        Assert.Empty((await ReadProviderAsync<UnmatchedEntry[]>(unmatched))!);
    }

    private sealed record RemovedResponse(int Removed);
}
