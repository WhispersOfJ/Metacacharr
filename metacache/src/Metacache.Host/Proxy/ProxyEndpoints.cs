using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;

namespace Metacache.Host.Proxy;

public static class ProxyEndpoints
{
    /// <summary>
    /// Maps proxy admin endpoints: status (which hostnames are routed, port, cert info)
    /// and the CA cert download for trust store installation.
    /// </summary>
    public static IEndpointRouteBuilder MapProxyEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/proxy/status", (ProxyRouter router, CertManager certs) =>
        {
            var hostnames = router.Hostnames.Select(h => new
            {
                Hostname = h,
                Upstream = router.Resolve(h),
                HasCert = true // all routed hosts get certs on demand
            });
            return Results.Json(new
            {
                routedHostnames = hostnames,
                caSubject = certs.CACert.Subject,
                caThumbprint = certs.CACert.Thumbprint,
                caNotAfter = certs.CACert.NotAfter
            });
        });

        // Download the CA cert (PEM format) for trust store installation
        endpoints.MapGet("/proxy/ca-cert", (CertManager certs) =>
        {
            string pem = certs.CACert.ExportCertificatePem();
            return Results.Text(pem, "application/x-pem-file");
        });

        return endpoints;
    }
}
