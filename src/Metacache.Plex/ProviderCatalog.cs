using Metacache.Core;
using Metacache.Plex.Models;

namespace Metacache.Plex;

/// <summary>
/// The MediaProvider definitions Plex fetches from GET /movie and GET /tv.
/// M0 advertises the two required features (metadata, match); the collection
/// feature is added once collections are implemented (see DESIGN.md §6).
/// </summary>
public static class ProviderCatalog
{
    // Declared before Movie/Tv: static initializers run in declaration order.
    private static readonly IReadOnlyList<ProviderFeature> Features =
    [
        new("metadata", "/library/metadata"),
        new("match", "/library/metadata/matches")
    ];

    public static MediaProviderResponse Movie { get; } = new(new MediaProviderDefinition(
        ProviderIdentities.Movie,
        "Metacache Movie Provider",
        ProviderIdentities.Version,
        [new ProviderType(PlexTypes.Movie, [new ProviderScheme(ProviderIdentities.Movie)])],
        Features));

    public static MediaProviderResponse Tv { get; } = new(new MediaProviderDefinition(
        ProviderIdentities.Tv,
        "Metacache TV Provider",
        ProviderIdentities.Version,
        [
            new ProviderType(PlexTypes.Show, [new ProviderScheme(ProviderIdentities.Tv)]),
            new ProviderType(PlexTypes.Season, [new ProviderScheme(ProviderIdentities.Tv)]),
            new ProviderType(PlexTypes.Episode, [new ProviderScheme(ProviderIdentities.Tv)])
        ],
        Features));
}
