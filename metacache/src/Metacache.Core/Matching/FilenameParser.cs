using System.Globalization;
using System.Text.RegularExpressions;

namespace Metacache.Core.Matching;

/// <summary>Year, season/episode numbers and normalized title tokens from a media path.</summary>
public sealed record ParsedFilename(
    int? Year,
    IReadOnlySet<string> Tokens,
    int? Season = null,
    int? Episode = null);

/// <summary>
/// Extracts matching hints from a Plex-provided relative file path, e.g.
/// `Movies/Back to the Future (1985)/Back.to.the.Future.1985.1080p.BluRay.mkv`
/// → year 1985, tokens {back, to, the, future}; and
/// `TV/Adventure Time/Adventure.Time.S01E01.mkv` → season 1, episode 1.
/// Well-known release tags (resolution/codec/source) are dropped; group names are not
/// (see DESIGN.md §15.6).
/// </summary>
public static partial class FilenameParser
{
    private static readonly HashSet<string> ReleaseTags = new(StringComparer.Ordinal)
    {
        "1080p", "720p", "2160p", "480p", "4k", "uhd",
        "bluray", "webdl", "webrip", "hdtv", "remux", "proper", "repack", "imax",
        "x264", "x265", "h264", "h265", "hevc", "avc", "10bit", "8bit",
        "dts", "dtshd", "truehd", "ac3", "aac", "flac", "atmos",
        "extended", "unrated", "dubbed", "subbed"
    };

    public static ParsedFilename Parse(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
            return new ParsedFilename(null, new HashSet<string>());

        string stem = Path.GetFileNameWithoutExtension(path);
        string spaced = SeparatorRegex().Replace(stem, " ");
        string normalized = TitleNormalizer.Normalize(spaced);

        int? season = null;
        int? episode = null;

        // Prefer the specific S01E01 form; fall back to "Season N".
        Match se = SEpisodeRegex().Match(normalized);
        if (se.Success)
        {
            season = int.Parse(se.Groups[1].Value, CultureInfo.InvariantCulture);
            episode = int.Parse(se.Groups[2].Value, CultureInfo.InvariantCulture);
            normalized = normalized.Remove(se.Index, se.Length);
        }
        else
        {
            Match seasonName = SeasonRegex().Match(normalized);
            if (seasonName.Success)
            {
                season = int.Parse(seasonName.Groups[1].Value, CultureInfo.InvariantCulture);
                normalized = normalized.Remove(seasonName.Index, seasonName.Length);
            }
        }

        int? year = null;
        Match yearMatch = YearRegex().Match(normalized);
        if (yearMatch.Success)
        {
            year = int.Parse(yearMatch.Value, CultureInfo.InvariantCulture);
            normalized = normalized.Remove(yearMatch.Index, yearMatch.Length);
        }

        var tokens = normalized
            .Split(' ', StringSplitOptions.RemoveEmptyEntries)
            .Where(t => !ReleaseTags.Contains(t))
            .ToHashSet();

        return new ParsedFilename(year, tokens, season, episode);
    }

    [GeneratedRegex(@"[\W_]+", RegexOptions.Compiled)]
    private static partial Regex SeparatorRegex();

    [GeneratedRegex(@"\bs(\d{1,2})e(\d{1,3})\b", RegexOptions.Compiled)]
    private static partial Regex SEpisodeRegex();

    [GeneratedRegex(@"\bseason\s+(\d{1,2})\b", RegexOptions.Compiled)]
    private static partial Regex SeasonRegex();

    [GeneratedRegex(@"\b(?:19|20)\d{2}\b", RegexOptions.Compiled)]
    private static partial Regex YearRegex();
}
