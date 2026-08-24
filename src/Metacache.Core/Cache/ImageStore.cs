using System.Text.RegularExpressions;

namespace Metacache.Core.Cache;

/// <summary>
/// Content-addressed image files on disk (DESIGN.md §7.3): `{root}/{first2}/{sha256}`.
/// Extensionless by design — content type is derived from the original upstream URL
/// (stored in the `urls` table) when serving. Files are written atomically (temp + move)
/// so a crash never leaves a half-written image under its final name.
/// </summary>
public sealed partial class ImageStore
{
    private readonly string _root;
    private readonly long _maxFileBytes;

    public ImageStore(string rootDirectory, long maxFileBytes)
    {
        _root = Path.GetFullPath(rootDirectory);
        _maxFileBytes = maxFileBytes;
        Directory.CreateDirectory(_root);
    }

    public string Root => _root;

    public long MaxFileBytes => _maxFileBytes;

    public static bool IsValidHash(string hash) =>
        !string.IsNullOrEmpty(hash) && HashRegex().IsMatch(hash);

    public string GetFilePath(string hash)
    {
        if (!IsValidHash(hash))
            throw new ArgumentException("Image hash must be 64 lowercase hex characters", nameof(hash));
        return Path.Combine(_root, hash[..2], hash);
    }

    public bool Exists(string hash) => IsValidHash(hash) && File.Exists(GetFilePath(hash));

    /// <summary>Writes the image, enforcing the per-file cap. Returns the stored path.</summary>
    public string Store(string hash, byte[] body)
    {
        if (!IsValidHash(hash))
            throw new ArgumentException("Image hash must be 64 lowercase hex characters", nameof(hash));
        if (body.Length > _maxFileBytes)
            throw new ImageTooLargeException(body.Length, _maxFileBytes);

        string path = GetFilePath(hash);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);

        string temp = path + ".tmp." + Guid.NewGuid().ToString("N");
        File.WriteAllBytes(temp, body);
        File.Move(temp, path, overwrite: true);
        return path;
    }

    public void Delete(string hash)
    {
        if (!IsValidHash(hash))
            return;
        string path = GetFilePath(hash);
        if (File.Exists(path))
            File.Delete(path);
    }

    [GeneratedRegex("^[0-9a-f]{64}$", RegexOptions.Compiled)]
    private static partial Regex HashRegex();
}

/// <summary>Raised when an upstream image exceeds the configured per-file cap.</summary>
public sealed class ImageTooLargeException : Exception
{
    public long Size { get; }

    public long Limit { get; }

    public ImageTooLargeException(long size, long limit)
        : base($"Image is {size} bytes, exceeding the {limit}-byte cap")
    {
        Size = size;
        Limit = limit;
    }
}
