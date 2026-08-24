namespace Metacache.Core.Matching;

/// <summary>
/// Pure scoring engine (DESIGN.md §15). Ranks <see cref="MatchCandidate"/>s against a
/// <see cref="MatchHint"/>: weighted title/year/filename/popularity for movies and shows;
/// show-title + structural index/air-date gating for seasons and episodes. Exact
/// external-GUID override, adult filtering, and manual/auto shaping are shared across
/// kinds.
/// </summary>
public static class MatchScorer
{
    public static IReadOnlyList<ScoredMatch> Score(
        MatchHint hint, IReadOnlyList<MatchCandidate> candidates, MatchPolicy? policy = null)
    {
        ArgumentNullException.ThrowIfNull(hint);
        ArgumentNullException.ThrowIfNull(candidates);
        MatchPolicy p = policy ?? MatchPolicy.Default;

        var scored = new List<ScoredMatch>(candidates.Count);
        foreach (MatchCandidate candidate in candidates)
        {
            if (candidate.Adult && !hint.IncludeAdult)
                continue;
            scored.Add(ScoreOne(hint, candidate, p));
        }

        return RankAndFilter(scored, hint, p);
    }

    /// <summary>Best auto-match, or null when nothing clears the threshold.</summary>
    public static ScoredMatch? BestMatch(
        MatchHint hint, IReadOnlyList<MatchCandidate> candidates, MatchPolicy? policy = null) =>
        Score(hint, candidates, policy).FirstOrDefault();

    private static ScoredMatch ScoreOne(MatchHint hint, MatchCandidate candidate, MatchPolicy policy)
    {
        // Exact external ID (imdb://, tmdb://, tvdb://) pins the item regardless of kind.
        if (hint.ExternalGuids.Any(g => candidate.ExternalIds.Contains(g, StringComparer.OrdinalIgnoreCase)))
            return new ScoredMatch(candidate, 1.0, new MatchBreakdown(1, 1, 1, 1, 0, GuidExact: true));

        return hint.Kind switch
        {
            MatchKind.Season => ScoreSeasonOne(hint, candidate, policy),
            MatchKind.Episode => ScoreEpisodeOne(hint, candidate, policy),
            _ => ScoreMovieOne(hint, candidate, policy)
        };
    }

    private static ScoredMatch ScoreMovieOne(MatchHint hint, MatchCandidate candidate, MatchPolicy p)
    {
        ParsedFilename? file = hint.Filename is null ? null : FilenameParser.Parse(hint.Filename);
        string? normalizedTitle = hint.Title is null ? null : TitleNormalizer.Normalize(hint.Title);

        double titleScore = normalizedTitle is null
            ? 0.5
            : Math.Max(
                TitleNormalizer.Similarity(normalizedTitle, candidate.Title),
                candidate.OriginalTitle is null ? 0 : TitleNormalizer.Similarity(normalizedTitle, candidate.OriginalTitle));

        double yearScore = ScoreYear(hint.Year, candidate.Year);
        double filenameScore = file is null ? 0.5 : ScoreFilename(file, candidate);
        double popularityScore = ScorePopularity(candidate.Popularity);
        double languageBonus = ScoreLanguage(hint.Language, candidate.OriginalLanguage, p);

        double total = Clamp01(
            p.TitleWeight * titleScore
            + p.YearWeight * yearScore
            + p.FilenameWeight * filenameScore
            + p.PopularityWeight * popularityScore
            + languageBonus);

        return new ScoredMatch(candidate, total,
            new MatchBreakdown(titleScore, yearScore, filenameScore, popularityScore, languageBonus, GuidExact: false));
    }

    private static ScoredMatch ScoreSeasonOne(MatchHint hint, MatchCandidate candidate, MatchPolicy p)
    {
        ParsedFilename? file = hint.Filename is null ? null : FilenameParser.Parse(hint.Filename);
        string showTitle = candidate.ParentTitle ?? candidate.Title;

        double titleScore = hint.ParentTitle is null
            ? 0.5
            : TitleNormalizer.Similarity(hint.ParentTitle, showTitle);
        double structureScore = IndexMatch(hint.Index ?? file?.Season, candidate.Index);
        double filenameScore = file is null
            ? 0.5
            : TitleNormalizer.TokenJaccard(string.Join(' ', file.Tokens), TitleNormalizer.Normalize(showTitle));
        double popularityScore = ScorePopularity(candidate.Popularity);

        double total = Clamp01(
            p.TvTitleWeight * titleScore
            + p.TvStructureWeight * structureScore
            + p.TvFilenameWeight * filenameScore
            + p.TvPopularityWeight * popularityScore);

        return new ScoredMatch(candidate, total,
            new MatchBreakdown(titleScore, Year: 0, filenameScore, popularityScore, 0, GuidExact: false, Structure: structureScore));
    }

    private static ScoredMatch ScoreEpisodeOne(MatchHint hint, MatchCandidate candidate, MatchPolicy p)
    {
        ParsedFilename? file = hint.Filename is null ? null : FilenameParser.Parse(hint.Filename);
        string showTitle = candidate.ParentTitle ?? candidate.Title;

        double titleScore = hint.GrandparentTitle is null
            ? 0.5
            : TitleNormalizer.Similarity(hint.GrandparentTitle, showTitle);
        double structureScore = EpisodeStructure(hint, candidate, file);
        double filenameScore = file is null
            ? 0.5
            : TitleNormalizer.TokenJaccard(string.Join(' ', file.Tokens), TitleNormalizer.Normalize(showTitle));
        double popularityScore = ScorePopularity(candidate.Popularity);

        double total = Clamp01(
            p.TvTitleWeight * titleScore
            + p.TvStructureWeight * structureScore
            + p.TvFilenameWeight * filenameScore
            + p.TvPopularityWeight * popularityScore);

        return new ScoredMatch(candidate, total,
            new MatchBreakdown(titleScore, Year: 0, filenameScore, popularityScore, 0, GuidExact: false, Structure: structureScore));
    }

    /// <summary>
    /// Episode structure: index hints (request first, then filename SxxEyy) gate on
    /// season+episode; with only an air date, gate on exact date equality.
    /// </summary>
    private static double EpisodeStructure(MatchHint hint, MatchCandidate candidate, ParsedFilename? file)
    {
        int? wantSeason = hint.ParentIndex ?? file?.Season;
        int? wantEpisode = hint.Index ?? file?.Episode;
        bool hasIndexHints = wantSeason is not null || wantEpisode is not null;

        if (hasIndexHints)
            return 0.5 * IndexMatch(wantSeason, candidate.ParentIndex)
                 + 0.5 * IndexMatch(wantEpisode, candidate.Index);

        if (hint.AirDate is not null)
        {
            if (candidate.AirDate is null)
                return 0.5;
            return string.Equals(hint.AirDate, candidate.AirDate, StringComparison.Ordinal) ? 1.0 : 0.0;
        }

        return 0.5;
    }

    private static double IndexMatch(int? want, int? have)
    {
        if (want is null || have is null)
            return 0.5;
        return want.Value == have.Value ? 1.0 : 0.0;
    }

    private static double ScoreYear(int? hintYear, int? candidateYear)
    {
        if (hintYear is null || candidateYear is null)
            return 0.5;

        int diff = Math.Abs(hintYear.Value - candidateYear.Value);
        return diff == 0 ? 1.0 : diff == 1 ? 0.4 : 0.0;
    }

    private static double ScoreFilename(ParsedFilename file, MatchCandidate candidate)
    {
        double yearPart = (file.Year is null || candidate.Year is null)
            ? 0.5
            : file.Year.Value == candidate.Year.Value
                ? 1.0
                : Math.Abs(file.Year.Value - candidate.Year.Value) == 1 ? 0.4 : 0.0;

        double tokenPart = TitleNormalizer.TokenJaccard(
            string.Join(' ', file.Tokens), TitleNormalizer.Normalize(candidate.Title));

        return 0.6 * yearPart + 0.4 * tokenPart;
    }

    private static double ScorePopularity(double popularity) =>
        1 - Math.Exp(-popularity / 200);

    private static double ScoreLanguage(string? hintLanguage, string? candidateLanguage, MatchPolicy policy)
    {
        if (hintLanguage is null || candidateLanguage is null)
            return 0;

        string hintTag = hintLanguage.Split('-')[0];
        return string.Equals(hintTag, candidateLanguage, StringComparison.OrdinalIgnoreCase)
            ? policy.LanguageBonus
            : 0;
    }

    private static IReadOnlyList<ScoredMatch> RankAndFilter(List<ScoredMatch> scored, MatchHint hint, MatchPolicy policy)
    {
        // Rank: score desc, then popularity desc, then stable input order.
        scored.Sort((a, b) =>
        {
            int byScore = b.Score.CompareTo(a.Score);
            return byScore != 0 ? byScore : b.Candidate.Popularity.CompareTo(a.Candidate.Popularity);
        });

        if (hint.Manual)
            return scored.Where(r => r.Score >= policy.ManualMinScore).Take(policy.MaxManualResults).ToList();

        ScoredMatch? best = scored.FirstOrDefault(r => r.Score >= policy.AutoMatchThreshold);
        return best is null ? [] : [best];
    }

    private static double Clamp01(double value) => Math.Clamp(value, 0.0, 1.0);
}
