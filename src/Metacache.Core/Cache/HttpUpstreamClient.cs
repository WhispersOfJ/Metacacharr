using System.Net;

namespace Metacache.Core.Cache;

/// <summary>
/// Production <see cref="IUpstreamHttp"/> over <see cref="HttpClient"/>. Thin: it forms
/// conditional requests, returns the body/validators, and surfaces 304s to the gateway.
/// Intended to be shared (one instance per process) so connection pooling applies.
/// </summary>
public sealed class HttpUpstreamClient : IUpstreamHttp, IDisposable
{
    private readonly HttpClient _http;

    public HttpUpstreamClient(HttpClient http) => _http = http;

    public async Task<UpstreamResponse> SendAsync(UpstreamRequest request, CancellationToken cancellationToken)
    {
        using var message = new HttpRequestMessage(HttpMethod.Get, request.Url);
        if (!string.IsNullOrEmpty(request.IfNoneMatch))
            message.Headers.TryAddWithoutValidation("If-None-Match", request.IfNoneMatch);
        if (request.IfModifiedSince is { } modified)
            message.Headers.IfModifiedSince = modified;

        using var response = await _http.SendAsync(message, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
            .ConfigureAwait(false);

        byte[] body = response.StatusCode == HttpStatusCode.NotModified
            ? []
            : await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);

        DateTimeOffset? retryAfter = null;
        if (response.Headers.RetryAfter is { } retry)
            retryAfter = retry.Date ?? (retry.Delta is { } delta ? DateTimeOffset.UtcNow.Add(delta) : null);

        return new UpstreamResponse(
            (int)response.StatusCode,
            body,
            response.Content.Headers.ContentType?.MediaType,
            response.Headers.ETag?.Tag,
            response.Content.Headers.LastModified,
            retryAfter);
    }

    public void Dispose() => _http.Dispose();
}
