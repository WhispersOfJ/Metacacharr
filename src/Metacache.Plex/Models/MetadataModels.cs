using System.Text.Json.Serialization;

namespace Metacache.Plex.Models;

/// <summary>
/// Wire models for Plex's metadata/match/image responses (docs/Metadata.md in
/// plexinc/tmdb-example-provider). Same hard rule as MediaProviderDefinition.cs:
/// this file is where Plex's provider schema lives — leaf attributes are camelCase,
/// collections are PascalCase, all pinned with explicit names. Nulls are omitted by
/// the web JSON defaults (Plex treats absent == "not provided").
/// </summary>
public sealed record MetadataContainerResponse(
    [property: JsonPropertyName("MediaContainer")] MetadataContainer MediaContainer);

public sealed record ImageContainerResponse(
    [property: JsonPropertyName("MediaContainer")] ImageContainer MediaContainer);

public sealed record MetadataContainer(
    [property: JsonPropertyName("offset")] int Offset,
    [property: JsonPropertyName("totalSize")] int TotalSize,
    [property: JsonPropertyName("identifier")] string Identifier,
    [property: JsonPropertyName("size")] int Size,
    [property: JsonPropertyName("Metadata")] IReadOnlyList<MetadataItem> Metadata);

public sealed record ImageContainer(
    [property: JsonPropertyName("offset")] int Offset,
    [property: JsonPropertyName("totalSize")] int TotalSize,
    [property: JsonPropertyName("identifier")] string Identifier,
    [property: JsonPropertyName("size")] int Size,
    [property: JsonPropertyName("Image")] IReadOnlyList<ImageAsset> Image);

public sealed record MetadataItem(
    [property: JsonPropertyName("ratingKey")] string RatingKey,
    [property: JsonPropertyName("key")] string Key,
    [property: JsonPropertyName("guid")] string Guid,
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("originallyAvailableAt")] string? OriginallyAvailableAt = null,
    [property: JsonPropertyName("thumb")] string? Thumb = null,
    [property: JsonPropertyName("art")] string? Art = null,
    [property: JsonPropertyName("contentRating")] string? ContentRating = null,
    [property: JsonPropertyName("originalTitle")] string? OriginalTitle = null,
    [property: JsonPropertyName("titleSort")] string? TitleSort = null,
    [property: JsonPropertyName("year")] int? Year = null,
    [property: JsonPropertyName("summary")] string? Summary = null,
    [property: JsonPropertyName("isAdult")] bool? IsAdult = null,
    [property: JsonPropertyName("duration")] int? Duration = null,
    [property: JsonPropertyName("tagline")] string? Tagline = null,
    [property: JsonPropertyName("studio")] string? Studio = null,
    [property: JsonPropertyName("theme")] string? Theme = null,
    [property: JsonPropertyName("parentRatingKey")] string? ParentRatingKey = null,
    [property: JsonPropertyName("parentKey")] string? ParentKey = null,
    [property: JsonPropertyName("parentGuid")] string? ParentGuid = null,
    [property: JsonPropertyName("parentType")] string? ParentType = null,
    [property: JsonPropertyName("parentTitle")] string? ParentTitle = null,
    [property: JsonPropertyName("parentThumb")] string? ParentThumb = null,
    [property: JsonPropertyName("index")] int? Index = null,
    [property: JsonPropertyName("grandparentRatingKey")] string? GrandparentRatingKey = null,
    [property: JsonPropertyName("grandparentKey")] string? GrandparentKey = null,
    [property: JsonPropertyName("grandparentGuid")] string? GrandparentGuid = null,
    [property: JsonPropertyName("grandparentType")] string? GrandparentType = null,
    [property: JsonPropertyName("grandparentTitle")] string? GrandparentTitle = null,
    [property: JsonPropertyName("grandparentThumb")] string? GrandparentThumb = null,
    [property: JsonPropertyName("parentIndex")] int? ParentIndex = null,
    [property: JsonPropertyName("Image")] IReadOnlyList<ImageAsset>? Image = null,
    [property: JsonPropertyName("Genre")] IReadOnlyList<GenreItem>? Genre = null,
    [property: JsonPropertyName("Guid")] IReadOnlyList<GuidItem>? GuidItems = null,
    [property: JsonPropertyName("Rating")] IReadOnlyList<RatingItem>? Rating = null,
    [property: JsonPropertyName("Role")] IReadOnlyList<PersonItem>? Role = null,
    [property: JsonPropertyName("Director")] IReadOnlyList<PersonItem>? Director = null,
    [property: JsonPropertyName("Producer")] IReadOnlyList<PersonItem>? Producer = null,
    [property: JsonPropertyName("Writer")] IReadOnlyList<PersonItem>? Writer = null,
    [property: JsonPropertyName("Country")] IReadOnlyList<CountryItem>? Country = null,
    [property: JsonPropertyName("Studio")] IReadOnlyList<StudioItem>? StudioItems = null,
    [property: JsonPropertyName("Collection")] IReadOnlyList<CollectionItem>? Collection = null,
    [property: JsonPropertyName("Network")] IReadOnlyList<NetworkItem>? Network = null,
    [property: JsonPropertyName("SeasonType")] IReadOnlyList<SeasonTypeItem>? SeasonType = null,
    [property: JsonPropertyName("Children")] ChildrenObject? Children = null);

public sealed record ImageAsset(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("url")] string Url,
    [property: JsonPropertyName("alt")] string? Alt = null);

public sealed record GenreItem(
    [property: JsonPropertyName("tag")] string Tag,
    [property: JsonPropertyName("originalTag")] string? OriginalTag = null);

public sealed record GuidItem(
    [property: JsonPropertyName("id")] string Id);

public sealed record RatingItem(
    [property: JsonPropertyName("image")] string Image,
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("value")] double Value);

public sealed record PersonItem(
    [property: JsonPropertyName("tag")] string Tag,
    [property: JsonPropertyName("thumb")] string? Thumb = null,
    [property: JsonPropertyName("role")] string? Role = null,
    [property: JsonPropertyName("order")] int? Order = null);

public sealed record CountryItem(
    [property: JsonPropertyName("tag")] string Tag);

public sealed record StudioItem(
    [property: JsonPropertyName("tag")] string Tag);

public sealed record CollectionItem(
    [property: JsonPropertyName("guid")] string Guid,
    [property: JsonPropertyName("key")] string Key,
    [property: JsonPropertyName("tag")] string Tag,
    [property: JsonPropertyName("summary")] string? Summary = null,
    [property: JsonPropertyName("art")] string? Art = null,
    [property: JsonPropertyName("thumb")] string? Thumb = null);

public sealed record NetworkItem(
    [property: JsonPropertyName("tag")] string Tag);

public sealed record SeasonTypeItem(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("source")] string Source,
    [property: JsonPropertyName("tag")] string Tag,
    [property: JsonPropertyName("title")] string Title);

public sealed record ChildrenObject(
    [property: JsonPropertyName("size")] int Size,
    [property: JsonPropertyName("Metadata")] IReadOnlyList<MetadataItem> Metadata);
