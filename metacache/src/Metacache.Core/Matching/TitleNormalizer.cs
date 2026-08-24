using System.Text;
using System.Text.RegularExpressions;

namespace Metacache.Core.Matching;

/// <summary>
/// Title normalization and similarity (DESIGN.md §15.2): lowercase, smart quotes to
/// ASCII, non-alphanumerics to spaces, collapsed whitespace, leading articles stripped,
/// standalone roman numerals mapped to digits. Similarity is the max of token-Jaccard
/// (handles word order) and bigram-Dice (handles spelling variants).
/// </summary>
public static partial class TitleNormalizer
{
    public static string Normalize(string? title)
    {
        if (string.IsNullOrWhiteSpace(title))
            return string.Empty;

        var sb = new StringBuilder(title.Length);
        foreach (char ch in title.ToLowerInvariant())
            sb.Append(char.IsLetterOrDigit(ch) ? ch : ' ');

        string normalized = WhitespaceRegex().Replace(sb.ToString(), " ").Trim();
        normalized = StripLeadingArticle(normalized);
        return MapRomanNumerals(normalized);
    }

    public static IReadOnlySet<string> Tokens(string? title) =>
        Normalize(title).Split(' ', StringSplitOptions.RemoveEmptyEntries).ToHashSet();

    /// <summary>Similarity in [0,1] between two raw titles (normalized internally).</summary>
    public static double Similarity(string? a, string? b)
    {
        string na = Normalize(a);
        string nb = Normalize(b);
        if (string.Equals(na, nb, StringComparison.Ordinal))
            return 1.0;

        return Math.Max(TokenJaccard(na, nb), BigramDice(na, nb));
    }

    /// <summary>Token-set Jaccard over normalized titles.</summary>
    public static double TokenJaccard(string normalizedA, string normalizedB)
    {
        string[] ta = normalizedA.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        string[] tb = normalizedB.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (ta.Length == 0 && tb.Length == 0)
            return 1.0;
        if (ta.Length == 0 || tb.Length == 0)
            return 0.0;

        var setB = tb.ToHashSet();
        int intersection = ta.Count(t => setB.Contains(t));
        int union = ta.Length + tb.Length - intersection;
        return (double)intersection / union;
    }

    /// <summary>Bigram Dice coefficient over the normalized strings.</summary>
    public static double BigramDice(string a, string b)
    {
        if (a.Length < 2 && b.Length < 2)
            return string.Equals(a, b, StringComparison.Ordinal) ? 1.0 : 0.0;

        var bigramsB = new HashSet<string>();
        for (int i = 0; i + 1 < b.Length; i++)
            bigramsB.Add(b.Substring(i, 2));

        int common = 0;
        for (int i = 0; i + 1 < a.Length; i++)
        {
            if (bigramsB.Contains(a.Substring(i, 2)))
                common++;
        }

        return 2.0 * common / (Math.Max(1, a.Length - 1) + Math.Max(1, b.Length - 1));
    }

    private static string StripLeadingArticle(string normalized)
    {
        foreach (string article in LeadingArticles)
        {
            if (normalized.StartsWith(article, StringComparison.Ordinal))
                return normalized[article.Length..];
        }
        return normalized;
    }

    private static string MapRomanNumerals(string normalized)
    {
        return RomanTokenRegex().Replace(normalized, m =>
            TryParseRoman(m.Value, out int value) ? value.ToString() : m.Value);
    }

    private static bool TryParseRoman(string token, out int value)
    {
        value = 0;
        if (token.Length < 2)
            return false;

        int previous = 0;
        foreach (char ch in token)
        {
            if (!RomanMap.TryGetValue(ch, out int current))
                return false;
            value += current;
            if (previous != 0 && previous < current)
                value -= 2 * previous; // e.g. IV = 4, IX = 9
            previous = current;
        }

        return value is >= 2 and <= 39; // conservative: avoid single letters and big numbers
    }

    private static readonly string[] LeadingArticles = ["the ", "a ", "an "];

    private static readonly Dictionary<char, int> RomanMap = new()
    {
        ['i'] = 1,
        ['v'] = 5,
        ['x'] = 10,
        ['l'] = 50,
        ['c'] = 100,
        ['d'] = 500,
        ['m'] = 1000
    };

    [GeneratedRegex(@"\s+")]
    private static partial Regex WhitespaceRegex();

    [GeneratedRegex(@"(?<![\w])([ivxlcdm]{2,})(?![\w])", RegexOptions.IgnoreCase)]
    private static partial Regex RomanTokenRegex();
}
