"""Sync telemetry: one MDBListSyncLog row per import-list run (manual or
scheduled), plus the GET /api/mdblist/history read route - mirrors
services/letterboxd/sync.py, see models/mdblist_sync_log.py."""
from sqlalchemy.orm import Session

from models.mdblist_sync_log import MDBListSyncLog

HISTORY_PAGE_SIZE = 100


def record_sync_log(db: Session, list_url: str, *, radarr_added: int = 0, radarr_already: int = 0,
                     radarr_failed: int = 0, sonarr_added: int = 0, sonarr_already: int = 0,
                     sonarr_failed: int = 0, error_detail: str | None = None) -> None:
    db.add(MDBListSyncLog(
        list_url=list_url, radarr_added=radarr_added, radarr_already=radarr_already, radarr_failed=radarr_failed,
        sonarr_added=sonarr_added, sonarr_already=sonarr_already, sonarr_failed=sonarr_failed,
        error_detail=error_detail,
    ))
    db.commit()


def recent_sync_logs(db: Session) -> list[dict]:
    # Ordered by id, not run_at - same sqlite CURRENT_TIMESTAMP second-level
    # resolution reasoning as letterboxd's recent_sync_logs.
    rows = (
        db.query(MDBListSyncLog)
        .order_by(MDBListSyncLog.id.desc())
        .limit(HISTORY_PAGE_SIZE)
        .all()
    )
    return [
        {
            "listUrl": r.list_url,
            "runAt": r.run_at.isoformat() if r.run_at else None,
            "radarrAdded": r.radarr_added,
            "radarrAlready": r.radarr_already,
            "radarrFailed": r.radarr_failed,
            "sonarrAdded": r.sonarr_added,
            "sonarrAlready": r.sonarr_already,
            "sonarrFailed": r.sonarr_failed,
            "errorDetail": r.error_detail,
        }
        for r in rows
    ]
