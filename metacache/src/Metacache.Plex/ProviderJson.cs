using System.Text.Json;

namespace Metacache.Plex;

/// <summary>
/// Serializer options for provider responses. Built on the web defaults (camelCase,
/// nulls omitted) but with case-SENSITIVE property names: Plex's schema legitimately
/// carries both `guid` and `Guid` (and `studio`/`Studio`) in one object, and
/// System.Text.Json's default case-insensitive conflict check rejects those pairs.
/// All property names are pinned with explicit attributes, so the naming policy is
/// irrelevant — only the conflict comparison changes.
/// </summary>
public static class ProviderJson
{
    public static readonly JsonSerializerOptions Options =
        new(JsonSerializerDefaults.Web) { PropertyNameCaseInsensitive = false };
}
