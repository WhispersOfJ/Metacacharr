from fastapi.testclient import TestClient


def _login(client, main_module, password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200


def test_record_sync_log_writes_a_row(cp_main_app):
    from models.letterboxd_sync_log import LetterboxdSyncLog
    from services.letterboxd.sync import record_sync_log

    db = cp_main_app.SessionLocal()
    record_sync_log(db, "https://letterboxd.com/bear/watchlist/", matched=8, unmatched=1, added=3, already=5,
                     failed=0, tv_crossover=1)
    row = db.query(LetterboxdSyncLog).filter_by(list_url="https://letterboxd.com/bear/watchlist/").one()
    assert row.added == 3
    assert row.tv_crossover == 1
    db.close()


def test_history_endpoint_returns_runs_most_recent_first(cp_main_app):
    from services.letterboxd.sync import record_sync_log

    db = cp_main_app.SessionLocal()
    record_sync_log(db, "https://letterboxd.com/bear/list/a/", matched=1, unmatched=0, added=1, already=0, failed=0)
    record_sync_log(db, "https://letterboxd.com/bear/list/b/", matched=2, unmatched=0, added=2, already=0, failed=0)
    db.close()

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.get("/api/arr/letterboxd/history")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 2
    assert runs[0]["listUrl"] == "https://letterboxd.com/bear/list/b/"  # most recent first
