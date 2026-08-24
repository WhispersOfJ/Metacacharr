using System.Text.Json;

namespace Metacache.Plex.Warming;

/// <summary>
/// The part of a Plex webhook payload the predictive warmer cares about: the event
/// name and, for media.play, the played item. Fields map to Plex's webhook JSON
/// (§20): movie → `title`/`year` + `Guid[]`; episode → `grandparentTitle`
/// (the show), `parentIndex` (season), `index` (episode).
/// </summary>
public sealed record PlexWebhookPayload(string Event, PlexPlayMetadata? Metadata);

/// <summary>The played item's identity signals (all nullable — resolution is best-effort).</summary>
public sealed record PlexPlayMetadata(
    string Kind,
    string? Title,
    int? Year,
    IReadOnlyList<string> Guids,
    string? ShowTitle,
    int? Season,
    int? Episode);

/// <summary>
/// Parses a Plex webhook body (the JSON shape PMS posts to webhook URLs). Property
/// lookups are case-insensitive — Plex sends `Metadata`, `grandparentTitle`, and a
/// `Guid` array of `{ id, provider }` items, but tolerates variance between PMS
/// versions. Returns null when the body isn't valid JSON.
/// </summary>
public static class PlexPlayParser
{
    private static readonly JsonSerializerOptions Options = new() { PropertyNameCaseInsensitive = true };

    public static PlexWebhookPayload? Parse(string json)
    {
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(json);
        }
        catch (JsonException)
        {
            return null;
        }

        using (doc)
        {
            JsonElement root = doc.RootElement;
            string? evt = root.TryGetProperty("event", out JsonElement eventElement)
                ? eventElement.GetString()
                : null;
            if (evt is null)
                return null;

            PlexPlayMetadata? metadata = null;
            if (root.TryGetProperty("Metadata", out JsonElement meta))
                metadata = ParseMetadata(meta);
            return new PlexWebhookPayload(evt, metadata);
        }
    }

    private static PlexPlayMetadata? ParseMetadata(JsonElement meta)
    {
        string? type = GetString(meta, "type");
        if (type is not ("movie" or "episode"))
            return null;

        var guids = new List<string>();
        if (meta.TryGetProperty("Guid", out JsonElement guidArray) && guidArray.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement entry in guidArray.EnumerateArray())
            {
                string? id = GetString(entry, "id");
                if (id is not null && IsExternalGuid(id))
                    guids.Add(id);
            }
        }
        // Some agents put a provider guid directly in the legacy `guid` field.
        string? legacy = GetString(meta, "guid");
        if (legacy is not null && IsExternalGuid(legacy))
            guids.Add(legacy);

        return new PlexPlayMetadata(
            Kind: type,
            Title: GetString(meta, "title"),
            Year: GetInt(meta, "year"),
            Guids: guids,
            ShowTitle: GetString(meta, "grandparentTitle"),
            Season: GetInt(meta, "parentIndex"),
            Episode: GetInt(meta, "index"));
    }

    private static bool IsExternalGuid(string id) =>
        id.StartsWith("imdb://", StringComparison.OrdinalIgnoreCase)
        || id.StartsWith("tmdb://", StringComparison.OrdinalIgnoreCase)
        || id.StartsWith("tvdb://", StringComparison.OrdinalIgnoreCase);

    private static string? GetString(JsonElement element, string name) =>
        element.TryGetProperty(name, out JsonElement value) ? value.GetString() : null;

    private static int? GetInt(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value))
            return null;
        return value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out int result) ? result : null;
    }
}
