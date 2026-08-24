using System.Net;
using System.Net.Http.Json;
using Metacache.Plex.Models;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Metacache.Host.Tests;

public class ProviderDefinitionsTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    public ProviderDefinitionsTests(WebApplicationFactory<Program> factory) => _factory = factory;

    [Fact]
    public async Task Movie_definition_conforms_to_plex_contract()
    {
        var client = _factory.CreateClient();

        var response = await client.GetAsync("/movie");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var provider = (await response.Content.ReadFromJsonAsync<MediaProviderResponse>())!.MediaProvider;

        Assert.Equal("tv.plex.agents.custom.metacache.movie", provider.Identifier);
        Assert.Equal("Metacache Movie Provider", provider.Title);
        Assert.Equal("1.0.0", provider.Version);

        var movieType = Assert.Single(provider.Types);
        Assert.Equal(PlexTypes.Movie, movieType.Type);
        Assert.Equal(provider.Identifier, Assert.Single(movieType.Scheme).Scheme);

        Assert.Contains(provider.Feature, f => f is { Type: "metadata", Key: "/library/metadata" });
        Assert.Contains(provider.Feature, f => f is { Type: "match", Key: "/library/metadata/matches" });
    }

    [Fact]
    public async Task Tv_definition_supports_shows_seasons_and_episodes()
    {
        var client = _factory.CreateClient();

        var response = await client.GetAsync("/tv");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var provider = (await response.Content.ReadFromJsonAsync<MediaProviderResponse>())!.MediaProvider;

        Assert.Equal("tv.plex.agents.custom.metacache.tv", provider.Identifier);
        Assert.Collection(
            provider.Types,
            t => Assert.Equal(PlexTypes.Show, t.Type),
            t => Assert.Equal(PlexTypes.Season, t.Type),
            t => Assert.Equal(PlexTypes.Episode, t.Type));
        Assert.All(provider.Types, t => Assert.Equal(provider.Identifier, Assert.Single(t.Scheme).Scheme));
    }

    [Fact]
    public async Task Json_uses_exact_plex_property_casing()
    {
        var client = _factory.CreateClient();

        var raw = await client.GetStringAsync("/movie");

        Assert.Contains("\"MediaProvider\"", raw);
        Assert.Contains("\"identifier\"", raw);
        Assert.Contains("\"Types\"", raw);
        Assert.Contains("\"Scheme\"", raw);
        Assert.Contains("\"Feature\"", raw);
    }

    [Fact]
    public async Task Health_endpoint_responds_ok()
    {
        var client = _factory.CreateClient();

        var response = await client.GetAsync("/healthz");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("ok", await response.Content.ReadAsStringAsync());
    }
}
