using System.Text.Json.Serialization;

namespace Metacache.Plex.Models;

/// <summary>
/// Wire models for Plex's metadata-provider contract (PMS 1.43+).
/// Property names are locked to the exact casing Plex expects — the API itself is
/// mixed-case ("Types" vs "type", "Scheme" vs "scheme"), so explicit names are used
/// instead of a naming policy. This file is the ONLY place the provider schema
/// is touched (see DESIGN.md §11 "hard rule").
/// </summary>
public sealed record MediaProviderResponse(
    [property: JsonPropertyName("MediaProvider")] MediaProviderDefinition MediaProvider);

public sealed record MediaProviderDefinition(
    [property: JsonPropertyName("identifier")] string Identifier,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("Types")] IReadOnlyList<ProviderType> Types,
    [property: JsonPropertyName("Feature")] IReadOnlyList<ProviderFeature> Feature);

public sealed record ProviderType(
    [property: JsonPropertyName("type")] int Type,
    [property: JsonPropertyName("Scheme")] IReadOnlyList<ProviderScheme> Scheme);

public sealed record ProviderScheme(
    [property: JsonPropertyName("scheme")] string Scheme);

public sealed record ProviderFeature(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("key")] string Key);

/// <summary>Metadata type numbers defined by Plex.</summary>
public static class PlexTypes
{
    public const int Movie = 1;
    public const int Show = 2;
    public const int Season = 3;
    public const int Episode = 4;
    public const int Collection = 18;
}
