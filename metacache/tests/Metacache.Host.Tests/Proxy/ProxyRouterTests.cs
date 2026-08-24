using Metacache.Host.Proxy;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Metacache.Host.Tests.Proxy;

/// <summary>
/// Tests for the ARR proxy router: hostname→upstream mapping and URL reconstruction.
/// </summary>
public class ProxyRouterTests
{
    [Fact]
    public void Resolve_returns_upstream_for_known_hostname()
    {
        var router = new ProxyRouter(new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["api.themoviedb.org"] = "https://api.themoviedb.org/3",
            ["image.tmdb.org"] = "https://image.tmdb.org/t/p/original"
        });

        Assert.Equal("https://api.themoviedb.org/3", router.Resolve("api.themoviedb.org"));
        Assert.Equal("https://image.tmdb.org/t/p/original", router.Resolve("image.tmdb.org"));
    }

    [Fact]
    public void Resolve_returns_null_for_unknown_hostname()
    {
        var router = new ProxyRouter(new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["api.themoviedb.org"] = "https://api.themoviedb.org/3"
        });

        Assert.Null(router.Resolve("evil.com"));
        Assert.Null(router.Resolve(""));
        Assert.Null(router.Resolve(null!));
    }

    [Fact]
    public void Resolve_is_case_insensitive()
    {
        var router = new ProxyRouter(new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["api.themoviedb.org"] = "https://api.themoviedb.org/3"
        });

        Assert.Equal("https://api.themoviedb.org/3", router.Resolve("API.THEMOVIEDB.ORG"));
    }

    [Fact]
    public void ReconstructUrl_builds_correct_full_url()
    {
        var router = new ProxyRouter(new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["api.themoviedb.org"] = "https://api.themoviedb.org/3"
        });

        string url = router.ReconstructUrl("api.themoviedb.org", "/movie/123", new QueryString("?language=en-US"));
        Assert.Equal("https://api.themoviedb.org/3/movie/123?language=en-US", url);
    }

    [Fact]
    public void ReconstructUrl_handles_trailing_slash_in_base()
    {
        var router = new ProxyRouter(new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["image.tmdb.org"] = "https://image.tmdb.org/t/p/original/"
        });

        string url = router.ReconstructUrl("image.tmdb.org", "/abc.png", new QueryString());
        Assert.Equal("https://image.tmdb.org/t/p/original/abc.png", url);
    }

    [Fact]
    public void ReconstructUrl_throws_for_unknown_hostname()
    {
        var router = new ProxyRouter(new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase));
        Assert.Throws<InvalidOperationException>(() =>
            router.ReconstructUrl("evil.com", "/path", new()));
    }

    [Fact]
    public void Hostnames_returns_all_mapped_hosts()
    {
        var router = new ProxyRouter(new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["api.themoviedb.org"] = "https://api.themoviedb.org/3",
            ["api.thetvdb.com"] = "https://api4.thetvdb.com"
        });

        var hosts = router.Hostnames.ToList();
        Assert.Equal(2, hosts.Count);
        Assert.Contains("api.themoviedb.org", hosts);
        Assert.Contains("api.thetvdb.com", hosts);
    }

    [Fact]
    public void FromConfig_loads_default_routes()
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Routes:TmdbApi"] = "https://api.themoviedb.org/3",
            ["Routes:TvdbApi"] = "https://api4.thetvdb.com"
        }).Build();

        var router = ProxyRouter.FromConfig(config.GetSection("Routes"));

        Assert.Equal("https://api.themoviedb.org/3", router.Resolve("api.themoviedb.org"));
        Assert.Equal("https://api4.thetvdb.com", router.Resolve("api.thetvdb.com"));
        Assert.Equal("https://image.tmdb.org/t/p/original", router.Resolve("image.tmdb.org"));
        Assert.Equal("https://webservice.fanart.tv/v3", router.Resolve("webservice.fanart.tv"));
    }
}
