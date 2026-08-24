from types import SimpleNamespace


def _guid(gid):
    return SimpleNamespace(id=gid)


def test_existing_tmdb_id_reads_new_agent_guid(audit_tmdb_links):
    movie = SimpleNamespace(guids=[_guid("imdb://tt1234"), _guid("tmdb://5678")], guid="")
    assert audit_tmdb_links.existing_tmdb_id(movie) == 5678


def test_existing_tmdb_id_falls_back_to_legacy_agent_guid(audit_tmdb_links):
    movie = SimpleNamespace(guids=[], guid="com.plexapp.agents.themoviedb://9999?lang=en")
    assert audit_tmdb_links.existing_tmdb_id(movie) == 9999


def test_existing_tmdb_id_none_when_no_link_present(audit_tmdb_links):
    movie = SimpleNamespace(guids=[_guid("imdb://tt1234")], guid="local://abc")
    assert audit_tmdb_links.existing_tmdb_id(movie) is None


def test_normalize_title_strips_punctuation_and_leading_article(audit_tmdb_links):
    assert audit_tmdb_links.normalize_title("The Matrix: Reloaded!") == "matrix reloaded"


def test_normalize_title_only_strips_leading_article_not_mid_title(audit_tmdb_links):
    assert audit_tmdb_links.normalize_title("A Man Called A") == "man called a"


def test_best_candidate_picks_highest_scoring_result(audit_tmdb_links):
    results = [
        {"title": "Something Else", "release_date": "2020-01-01"},
        {"title": "The Matrix", "release_date": "1999-03-31"},
    ]
    cand, ratio, year_delta = audit_tmdb_links.best_candidate(results, "The Matrix", 1999)
    assert cand["title"] == "The Matrix"
    assert ratio == 1.0
    assert year_delta == 0


def test_best_candidate_penalizes_year_mismatch(audit_tmdb_links):
    results = [
        {"title": "The Matrix", "release_date": "1989-01-01"},
        {"title": "The Matrix", "release_date": "1999-03-31"},
    ]
    cand, ratio, year_delta = audit_tmdb_links.best_candidate(results, "The Matrix", 1999)
    assert year_delta == 0


def test_best_candidate_returns_none_below_min_ratio(audit_tmdb_links):
    results = [{"title": "Completely Unrelated Title", "release_date": "2020-01-01"}]
    assert audit_tmdb_links.best_candidate(results, "The Matrix", 1999) is None


def test_best_candidate_returns_none_for_empty_results(audit_tmdb_links):
    assert audit_tmdb_links.best_candidate([], "The Matrix", 1999) is None


def test_confidence_label_high_for_close_match(audit_tmdb_links):
    assert audit_tmdb_links.confidence_label(0.95, 0) == "high"
    assert audit_tmdb_links.confidence_label(0.95, 1) == "high"


def test_confidence_label_medium_when_year_delta_too_large(audit_tmdb_links):
    assert audit_tmdb_links.confidence_label(0.95, 2) == "medium"


def test_confidence_label_medium_for_lower_ratio(audit_tmdb_links):
    assert audit_tmdb_links.confidence_label(0.70, 0) == "medium"


def test_confidence_label_high_when_year_unknown(audit_tmdb_links):
    assert audit_tmdb_links.confidence_label(0.95, None) == "high"
