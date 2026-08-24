using Metacache.Core.Cache;

namespace Metacache.Host.Tests.Cache;

public class ImageStoreTests : IDisposable
{
    private readonly string _dir;

    public ImageStoreTests() =>
        _dir = Path.Combine(Path.GetTempPath(), $"metacache-img-{Guid.NewGuid():N}");

    public void Dispose()
    {
        if (Directory.Exists(_dir))
            Directory.Delete(_dir, recursive: true);
    }

    [Fact]
    public void Store_writes_content_addressed_file()
    {
        var store = new ImageStore(_dir, maxFileBytes: 1024);
        string hash = UpstreamCache.ComputeKey("https://image.tmdb.org/t/p/original/abc.jpg");
        byte[] body = [1, 2, 3, 4];

        string path = store.Store(hash, body);

        Assert.Equal(Path.Combine(_dir, hash[..2], hash), path);
        Assert.True(store.Exists(hash));
        Assert.Equal(body, File.ReadAllBytes(path));
    }

    [Fact]
    public void Store_rejects_images_over_the_cap()
    {
        var store = new ImageStore(_dir, maxFileBytes: 4);

        ImageTooLargeException ex = Assert.Throws<ImageTooLargeException>(
            () => store.Store(UpstreamCache.ComputeKey("https://x/1.jpg"), [1, 2, 3, 4, 5]));

        Assert.Equal(5, ex.Size);
        Assert.Equal(4, ex.Limit);
    }

    [Theory]
    [InlineData("not-a-hash")]
    [InlineData("")]
    [InlineData("ABCDEF")]
    public void Invalid_hashes_are_rejected(string hash)
    {
        var store = new ImageStore(_dir, maxFileBytes: 1024);

        Assert.False(ImageStore.IsValidHash(hash));
        Assert.Throws<ArgumentException>(() => store.GetFilePath(hash));
        Assert.False(store.Exists(hash));
    }

    [Fact]
    public void Delete_removes_the_file()
    {
        var store = new ImageStore(_dir, maxFileBytes: 1024);
        string hash = UpstreamCache.ComputeKey("https://x/1.jpg");
        store.Store(hash, [1, 2, 3]);

        Assert.True(store.Exists(hash));

        store.Delete(hash);

        Assert.False(store.Exists(hash));
    }
}
