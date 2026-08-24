using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Metacache.Core.Cache;
using Metacache.Host.Tests.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests;

/// <summary>
/// Boots the real host with an in-memory cache and the fake TMDB upstream, so the
/// match/metadata/image endpoints are exercised end to end (DI wiring included).
/// </summary>
public abstract class ProviderEndpointTestBase : IDisposable
{
    protected readonly FakeUpstream Upstream = new();
    protected readonly WebApplicationFactory<Program> Factory;

    protected ProviderEndpointTestBase()
    {
        Factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("Metacache:DataPath", ":memory:");
                builder.UseSetting("Metacache:Tmdb:ApiKey", "test-api-key");
                builder.ConfigureTestServices(services => services.AddSingleton<IUpstreamHttp>(Upstream));
            });
        Upstream.Route();
    }

    public void Dispose() => Factory.Dispose();

    protected HttpClient Client => Factory.CreateClient();

    /// <summary>Case-sensitive, like the provider's own serializer (Plex schema has guid/Guid).</summary>
    protected static readonly JsonSerializerOptions TestJsonOptions =
        new(JsonSerializerDefaults.Web) { PropertyNameCaseInsensitive = false };

    protected static async Task<T?> ReadProviderAsync<T>(HttpResponseMessage response) =>
        await response.Content.ReadFromJsonAsync<T>(TestJsonOptions);

    protected static StringContent JsonBody(string json) => new(json, Encoding.UTF8, "application/json");
}
