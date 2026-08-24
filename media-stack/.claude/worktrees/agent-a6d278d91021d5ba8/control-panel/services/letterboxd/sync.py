"""Sync telemetry: one LetterboxdSyncLog row per add-from-letterboxd-list
run (manual or scheduled), plus the GET /api/arr/letterboxd/history read
route - see models/letterboxd_sync_log.py."""
from sqlalchemy.orm import Session

from models.letterboxd_sync_log import LetterboxdSyncLog

HISTORY_PAGE_SIZE = 100


def record_sync_log(db: Session, list_url: str, *, matched: int, unmatched: int, added: int, already: int,
                     failed: int, tv_crossover: int = 0, error_detail: str | None = None) -> None:
    db.add(LetterboxdSyncLog(list_url=list_url, matched=matched, unmatched=unmatched, added=added, already=already,
                              failed=failed, tv_crossover=tv_crossover, error_detail=error_detail))
    db.commit()


def recent_sync_logs(db: Session) -> list[dict]:
    # Ordered by id, not run_at - sqlite's CURRENT_TIMESTAMP default has
    # only second-level resolution, so two runs recorded within the same
    # second would tie on run_at; id is monotonic with insertion order
    # regardless of clock resolution.
    rows = (
        db.query(LetterboxdSyncLog)
        .order_by(LetterboxdSyncLog.id.desc())
        .limit(HISTORY_PAGE_SIZE)
        .all()
    )
    return [
        {
            "listUrl": r.list_url,
            "runAt": r.run_at.isoformat() if r.run_at else None,
            "matched": r.matched,
            "unmatched": r.unmatched,
            "added": r.added,
            "already": r.already,
            "failed": r.failed,
            "tvCrossover": r.tv_crossover,
            "errorDetail": r.error_detail,
        }
        for r in rows
    ]
