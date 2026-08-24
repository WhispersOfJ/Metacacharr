using Metacache.Core.Cache;
using Microsoft.AspNetCore.Connections;
using Microsoft.AspNetCore.Server.Kestrel.Https;

namespace Metacache.Host.Proxy;

public static class ProxyServiceCollectionExtensions
{
    /// <summary>
    /// Registers the ARR proxy face services: <see cref="ProxyRouter"/>,
    /// <see cref="CertManager"/>, and the <see cref="ProxyMiddleware"/> pipeline.
    /// </summary>
    public static IServiceCollection AddMetacacheProxy(
        this IServiceCollection services,
        ProxyOptions options,
        IConfigurationSection routeSection)
    {
        if (!options.Enabled)
            return services;

        var router = ProxyRouter.FromConfig(routeSection);
        services.AddSingleton(router);

        var certManager = new CertManager(Path.GetFullPath(options.CertDirectory));
        certManager.LoadPersistedCerts();
        services.AddSingleton(certManager);

        return services;
    }

    /// <summary>
    /// Configures Kestrel to listen on the proxy port with SNI-based TLS cert selection.
    /// </summary>
    public static void ConfigureProxyEndpoint(
        this WebApplicationBuilder builder,
        ProxyOptions options,
        CertManager certManager)
    {
        if (!options.Enabled)
            return;

        string bindAddress = options.BindAddress ?? "0.0.0.0";
        int port = options.HttpPort;

        builder.WebHost.ConfigureKestrel(kestrel =>
        {
            kestrel.ListenAnyIP(port, listenOptions =>
            {
                listenOptions.UseHttps(httpsOptions =>
                {
                    httpsOptions.ServerCertificateSelector = (context, sniHostname) =>
                    {
                        if (sniHostname is null)
                            return null;

                        // Check if this hostname is in our route table
                        var router = builder.Services.BuildServiceProvider().GetRequiredService<ProxyRouter>();
                        if (router.Resolve(sniHostname) is null)
                            return null;

                        return certManager.GetCert(sniHostname);
                    };
                });
            });
        });
    }

    /// <summary>
    /// Maps the proxy middleware into the pipeline. Must be called after UseRouting
    /// and before endpoint mapping so it can intercept requests that don't match
    /// local endpoints.
    /// </summary>
    public static IApplicationBuilder UseMetacacheProxy(this IApplicationBuilder app)
    {
        app.UseMiddleware<ProxyMiddleware>();
        return app;
    }
}
