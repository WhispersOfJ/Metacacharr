def test_letterboxd_tables_are_created(cp_main_app):
    from models.letterboxd_cache import LetterboxdTmdbCache
    from models.letterboxd_tracked_list import LetterboxdTrackedList
    from models.letterboxd_sync_log import LetterboxdSyncLog

    db = cp_main_app.SessionLocal()
    try:
        db.add(LetterboxdTmdbCache(slug="the-matrix", tmdb_id=603, media_type="movie"))
        db.add(LetterboxdTrackedList(url="https://letterboxd.com/bear/watchlist/", label="Bear's watchlist"))
        db.add(LetterboxdSyncLog(list_url="https://letterboxd.com/bear/watchlist/", matched=10, unmatched=1,
                                  added=5, already=4, failed=0, tv_crossover=1))
        db.commit()

        cache_row = db.query(LetterboxdTmdbCache).filter_by(slug="the-matrix").one()
        assert cache_row.tmdb_id == 603
        tracked_row = db.query(LetterboxdTrackedList).filter_by(url="https://letterboxd.com/bear/watchlist/").one()
        assert tracked_row.label == "Bear's watchlist"
        log_row = db.query(LetterboxdSyncLog).filter_by(list_url="https://letterboxd.com/bear/watchlist/").one()
        assert log_row.added == 5
    finally:
        db.close()
