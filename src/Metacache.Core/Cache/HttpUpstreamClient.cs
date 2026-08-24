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
        if (request.Headers is not null)
        {
            foreach (var (name, value) in request.Headers)
                message.Headers.TryAddWithoutValidation(name, value);
        }

        using var response = await _http.SendAsync(message, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
            .ConfigureAwait(false);

        byte[] body = response.StatusCode == HttpStatusCode.NotModified
            ? []
            : await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);

        DateTimeOffset? retryAfter = null;
        if (response.Headers.RetryAfter is { } retry)
            retryAfter = retry.Date ?? (retry.Delta is { } delta ? DateTimeOffset.UtcNow.Add(delta) : null);

        // Pass the response headers through (case-insensitive lookup) so consumers can
        // read provider-specific signals — e.g. TMDB's X-RateLimit-* for the gauge.
        var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var header in response.Headers)
            if (header.Value.Any())
                headers[header.Key] = string.Join(", ", header.Value);
        foreach (var header in response.Content.Headers)
            if (header.Value.Any())
                headers[header.Key] = string.Join(", ", header.Value);

        return new UpstreamResponse(
            (int)response.StatusCode,
            body,
            response.Content.Headers.ContentType?.MediaType,
            response.Headers.ETag?.Tag,
            response.Content.Headers.LastModified,
            retryAfter,
            headers);
    }

    public void Dispose() => _http.Dispose();
}
