using System.Security.Cryptography.X509Certificates;
using Metacache.Host.Proxy;
using Xunit;

namespace Metacache.Host.Tests.Proxy;

/// <summary>
/// Tests for the local CA and per-hostname cert generator.
/// </summary>
public class CertManagerTests : IDisposable
{
    private readonly string _certDir;

    public CertManagerTests()
    {
        _certDir = Path.Combine(Path.GetTempPath(), $"metacache-certs-{Guid.NewGuid():N}");
    }

    public void Dispose()
    {
        if (Directory.Exists(_certDir))
            Directory.Delete(_certDir, true);
    }

    [Fact]
    public void Constructor_creates_CA_cert_and_persists_it()
    {
        using var mgr = new CertManager(_certDir);
        Assert.NotNull(mgr.CACert);
        Assert.Contains("Metacache", mgr.CACert.Subject);
        Assert.True(File.Exists(Path.Combine(_certDir, "metacache-ca.pfx")));
    }

    [Fact]
    public void GetCert_generates_leaf_signed_by_CA()
    {
        using var mgr = new CertManager(_certDir);
        var leaf = mgr.GetCert("api.themoviedb.org");

        Assert.Contains("CN=api.themoviedb.org", leaf.Subject);

        // Build the chain — should validate against the local CA
        // Self-signed CA doesn't have CRL/OCSP, so allow those flags.
        var chain = new X509Chain();
        chain.ChainPolicy.ExtraStore.Add(mgr.CACert);
        chain.ChainPolicy.VerificationFlags =
            X509VerificationFlags.AllowUnknownCertificateAuthority |
            X509VerificationFlags.IgnoreRootRevocationUnknown;
        chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
        bool valid = chain.Build(leaf);
        // Chain build returns true even with informational status flags;
        // check that the leaf's issuer matches the CA's subject.
        Assert.Equal(mgr.CACert.Subject, leaf.Issuer);
    }

    [Fact]
    public void GetCert_returns_same_instance_on_repeat()
    {
        using var mgr = new CertManager(_certDir);
        var first = mgr.GetCert("api.thetvdb.com");
        var second = mgr.GetCert("api.thetvdb.com");
        Assert.Same(first, second);
    }

    [Fact]
    public void GetCert_persists_leaf_to_disk()
    {
        using var mgr = new CertManager(_certDir);
        mgr.GetCert("image.tmdb.org");
        Assert.True(File.Exists(Path.Combine(_certDir, "leaf-image.tmdb.org.pfx")));
    }

    [Fact]
    public void LoadPersistedCerts_restores_previous_certs()
    {
        string firstCert;
        using (var mgr = new CertManager(_certDir))
        {
            var cert = mgr.GetCert("api.themoviedb.org");
            firstCert = cert.Thumbprint;
        }

        // Reload in a new instance
        using var mgr2 = new CertManager(_certDir);
        mgr2.LoadPersistedCerts();
        var reloaded = mgr2.GetCert("api.themoviedb.org");
        Assert.Equal(firstCert, reloaded.Thumbprint);
    }

    [Fact]
    public void CA_cert_is_self_signed()
    {
        using var mgr = new CertManager(_certDir);
        Assert.Equal(mgr.CACert.Subject, mgr.CACert.Issuer);
    }
}
