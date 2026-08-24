using System.Text.Json;
using Metacache.Core.Matching;
using Metacache.Plex.Models;

namespace Metacache.Plex;

/// <summary>
/// Parses a Plex match request body (§6.3) into a <see cref="MatchHint"/>. Movies only
/// for M1 — other types return a descriptive error the endpoint turns into 400.
/// The `X-Plex-Language`/`X-Plex-Country` context is applied by the caller, not here.
/// </summary>
public static class MatchRequestParser
{
    public static bool TryParse(string body, out MatchHint hint, out bool includeChildren, out string? error)
    {
        hint = MatchHint.Empty;
        includeChildren = false;
        error = null;

        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(body);
        }
        catch (JsonException)
        {
            error = "Request body is not valid JSON.";
            return false;
        }

        using (doc)
        {
            JsonElement root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                error = "Request body must be a JSON object.";
                return false;
            }

            if (!root.TryGetProperty("type", out JsonElement typeElement)
                || typeElement.ValueKind != JsonValueKind.Number
                || !typeElement.TryGetInt32(out int type))
            {
                error = "Missing or invalid 'type' (1=movie, 2=show, 3=season, 4=episode).";
                return false;
            }

            MatchKind kind = type switch
            {
                PlexTypes.Movie => MatchKind.Movie,
                PlexTypes.Show => MatchKind.Show,
                PlexTypes.Season => MatchKind.Season,
                PlexTypes.Episode => MatchKind.Episode,
                _ => (MatchKind)(-1)
            };
            if ((int)kind < 0)
            {
                error = $"Unknown match type {type} (1=movie, 2=show, 3=season, 4=episode).";
                return false;
            }

            string? guid = GetString(root, "guid");
            hint = new MatchHint(
                Title: GetString(root, "title"),
                Year: GetInt(root, "year"),
                Filename: GetString(root, "filename"),
                ExternalGuids: guid is null ? [] : [guid],
                Manual: GetBool(root, "manual"),
                IncludeAdult: GetBool(root, "includeAdult"),
                Language: null, // set by the endpoint from X-Plex-Language
                Kind: kind,
                ParentTitle: GetString(root, "parentTitle"),
                GrandparentTitle: GetString(root, "grandparentTitle"),
                Index: GetInt(root, "index"),
                ParentIndex: GetInt(root, "parentIndex"),
                AirDate: GetString(root, "date"));
            includeChildren = GetBool(root, "includeChildren");
            return true;
        }
    }

    private static string? GetString(JsonElement root, string name) =>
        root.TryGetProperty(name, out JsonElement element) && element.ValueKind == JsonValueKind.String
            ? element.GetString()
            : null;

    private static int? GetInt(JsonElement root, string name) =>
        root.TryGetProperty(name, out JsonElement element) && element.ValueKind == JsonValueKind.Number
            && element.TryGetInt32(out int value)
            ? value
            : null;

    private static bool GetBool(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out JsonElement element))
            return false;
        return element.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Number => element.TryGetInt32(out int value) && value != 0,
            _ => false
        };
    }
}
