namespace Metacache.Core.Cache;

/// <summary>Abstraction over upstream HTTP so the cache gateway is unit-testable.</summary>
public interface IUpstreamHttp
{
    Task<UpstreamResponse> SendAsync(UpstreamRequest request, CancellationToken cancellationToken);
}

public sealed record UpstreamRequest(
    Uri Url,
    string? IfNoneMatch = null,
    DateTimeOffset? IfModifiedSince = null);

public sealed record UpstreamResponse(
    int StatusCode,
    byte[] Body,
    string? ContentType,
    string? ETag,
    DateTimeOffset? LastModified,
    DateTimeOffset? RetryAfter);

/// <summary>
/// Raised when upstream could not satisfy a request and no usable cache entry exists.
/// StatusCode 0 means a transport-level failure; 429/5xx carry the upstream status.
/// </summary>
public sealed class UpstreamException : Exception
{
    public int StatusCode { get; }

    public DateTimeOffset? RetryAfter { get; }

    public UpstreamException(int statusCode, DateTimeOffset? retryAfter = null, string? message = null)
        : base(message ?? $"Upstream request failed with status {statusCode}")
    {
        StatusCode = statusCode;
        RetryAfter = retryAfter;
    }
}
