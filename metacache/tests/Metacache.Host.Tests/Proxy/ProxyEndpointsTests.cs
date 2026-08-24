using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Metacache.Core.Cache;
using Metacache.Host.Proxy;
using Metacache.Host.Tests.Cache;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests.Proxy;

/// <summary>
/// Integration tests for the proxy admin endpoints (status + CA cert download).
/// </summary>
public class ProxyEndpointsTests : IDisposable
{
    private readonly string _imageDir;
    private readonly string _certDir;
    private readonly FakeUpstream _upstream = new();
    private readonly WebApplicationFactory<Program> _factory;

    public ProxyEndpointsTests()
    {
        _imageDir = Path.Combine(Path.GetTempPath(), $"metacache-proxy-{Guid.NewGuid():N}");
        _certDir = Path.Combine(Path.GetTempPath(), $"metacache-proxy-certs-{Guid.NewGuid():N}");
        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("Metacache:DataPath", ":memory:");
                builder.UseSetting("Metacache:Images:Directory", _imageDir);
                builder.UseSetting("Metacache:Proxy:Enabled", "true");
                builder.UseSetting("Metacache:Proxy:CertDirectory", _certDir);
                builder.UseSetting("Metacache:Tmdb:ApiKey", "test-api-key");
                builder.ConfigureTestServices(services => services.AddSingleton<IUpstreamHttp>(_ => _upstream));
            });
    }

    public void Dispose()
    {
        _factory.Dispose();
        if (Directory.Exists(_imageDir))
            Directory.Delete(_imageDir, true);
        if (Directory.Exists(_certDir))
            Directory.Delete(_certDir, true);
    }

    [Fact]
    public async Task Proxy_status_returns_routed_hostnames()
    {
        var client = _factory.CreateClient();
        var response = await client.GetAsync("/proxy/status");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        var hostnames = json.GetProperty("routedHostnames");
        Assert.True(hostnames.GetArrayLength() >= 4, "Should route at least 4 default hostnames");
    }

    [Fact]
    public async Task Proxy_ca_cert_returns_pem()
    {
        var client = _factory.CreateClient();
        var response = await client.GetAsync("/proxy/ca-cert");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/x-pem-file", response.Content.Headers.ContentType?.MediaType);

        string pem = await response.Content.ReadAsStringAsync();
        Assert.Contains("BEGIN CERTIFICATE", pem);
        Assert.Contains("END CERTIFICATE", pem);
        // Decode PEM and verify it's our CA cert by subject
        var cert = System.Security.Cryptography.X509Certificates.X509Certificate2.CreateFromPem(pem);
        Assert.Contains("Metacache", cert.Subject);
    }
}
