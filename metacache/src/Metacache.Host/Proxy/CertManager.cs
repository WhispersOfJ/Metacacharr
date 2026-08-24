using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

namespace Metacache.Host.Proxy;

/// <summary>
/// Manages per-hostname X.509 certificates for TLS termination on the proxy face.
/// Generates a local CA root certificate and per-hostname leaf certs signed by it.
/// The CA cert should be installed in the trust store of hosts running ARR apps / Plex
/// (DESIGN.md §10).
/// </summary>
public sealed class CertManager : IDisposable
{
    private readonly X509Certificate2 _caCert;
    private readonly Dictionary<string, X509Certificate2> _leafCerts = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _lock = new();
    private readonly string _certDirectory;

    public CertManager(string certDirectory)
    {
        _certDirectory = certDirectory;
        Directory.CreateDirectory(certDirectory);

        string caPath = Path.Combine(certDirectory, "metacache-ca.pfx");
        if (File.Exists(caPath))
        {
            byte[] caBytes = File.ReadAllBytes(caPath);
            _caCert = X509CertificateLoader.LoadPkcs12(caBytes, null, X509KeyStorageFlags.Exportable);
        }
        else
        {
            _caCert = GenerateCaCert();
            File.WriteAllBytes(caPath, _caCert.Export(X509ContentType.Pfx));
        }
    }

    /// <summary>The CA root certificate — install this into the trust store of client machines.</summary>
    public X509Certificate2 CACert => _caCert;

    /// <summary>
    /// Gets or generates a leaf certificate for the given hostname, signed by the local CA.
    /// </summary>
    public X509Certificate2 GetCert(string hostname)
    {
        lock (_lock)
        {
            if (_leafCerts.TryGetValue(hostname, out X509Certificate2? existing))
                return existing;

            X509Certificate2 cert = GenerateLeafCert(hostname);
            _leafCerts[hostname] = cert;

            // Persist for reuse across restarts
            string leafPath = Path.Combine(_certDirectory, $"leaf-{hostname}.pfx");
            File.WriteAllBytes(leafPath, cert.Export(X509ContentType.Pfx));
            return cert;
        }
    }

    /// <summary>
    /// Loads persisted leaf certs from disk (called on startup to populate the cache
    /// without regenerating).
    /// </summary>
    public void LoadPersistedCerts()
    {
        lock (_lock)
        {
            foreach (string file in Directory.GetFiles(_certDirectory, "leaf-*.pfx"))
            {
                string hostname = Path.GetFileNameWithoutExtension(file)["leaf-".Length..];
                if (!_leafCerts.ContainsKey(hostname))
                {
                    byte[] certBytes = File.ReadAllBytes(file);
                    var cert = X509CertificateLoader.LoadPkcs12(certBytes, null, X509KeyStorageFlags.Exportable);
                    _leafCerts[hostname] = cert;
                }
            }
        }
    }

    private X509Certificate2 GenerateCaCert()
    {
        using var rsa = RSA.Create(2048);
        var request = new CertificateRequest(
            "CN=Metacache Local CA, O=Metacache",
            rsa,
            HashAlgorithmName.SHA256,
            RSASignaturePadding.Pkcs1);

        request.CertificateExtensions.Add(
            new X509BasicConstraintsExtension(true, false, 0, false));

        var san = new SubjectAlternativeNameBuilder();
        san.AddDnsName("Metacache Local CA");
        request.CertificateExtensions.Add(san.Build());

        var cert = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddYears(-1), DateTimeOffset.UtcNow.AddYears(10));

        // Export/reimport to make the private key exportable on Linux
        byte[] pfxBytes = cert.Export(X509ContentType.Pfx);
        return X509CertificateLoader.LoadPkcs12(pfxBytes, null, X509KeyStorageFlags.Exportable);
    }

    private X509Certificate2 GenerateLeafCert(string hostname)
    {
        using var rsa = RSA.Create(2048);
        var request = new CertificateRequest(
            $"CN={hostname}",
            rsa,
            HashAlgorithmName.SHA256,
            RSASignaturePadding.Pkcs1);

        var san = new SubjectAlternativeNameBuilder();
        san.AddDnsName(hostname);
        request.CertificateExtensions.Add(san.Build());

        request.CertificateExtensions.Add(
            new X509KeyUsageExtension(
                X509KeyUsageFlags.DigitalSignature | X509KeyUsageFlags.KeyEncipherment, false));

        request.CertificateExtensions.Add(
            new X509EnhancedKeyUsageExtension(
                [new Oid("1.3.6.1.5.5.7.3.1")], false)); // Server Authentication

        // Sign with the CA cert — pass the issuer X509Certificate2 directly
        byte[] serialBytes = _caCert.SerialNumberBytes.ToArray();
        var leaf = request.Create(
            _caCert,
            _caCert.NotBefore,
            _caCert.NotAfter,
            serialBytes);

        // Build full chain and export
        byte[] pfxBytes = leaf.Export(X509ContentType.Pfx);
        return X509CertificateLoader.LoadPkcs12(pfxBytes, null, X509KeyStorageFlags.Exportable);
    }

    public void Dispose()
    {
        _caCert.Dispose();
        foreach (var cert in _leafCerts.Values)
            cert.Dispose();
    }
}
