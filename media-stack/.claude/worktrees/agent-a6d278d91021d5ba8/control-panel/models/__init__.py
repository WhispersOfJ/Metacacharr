"""SQLAlchemy models for the evolved control-panel backend. Imported here
so Base.metadata sees every table before Alembic autogenerate or
create_all runs - see core/db.py."""
from models.user import User  # noqa: F401
from models.setting import Setting  # noqa: F401
from models.api_key import ApiKey  # noqa: F401
from models.audit_log import AuditLog  # noqa: F401
from models.letterboxd_cache import LetterboxdTmdbCache  # noqa: F401
from models.letterboxd_tracked_list import LetterboxdTrackedList  # noqa: F401
from models.letterboxd_sync_log import LetterboxdSyncLog  # noqa: F401
from models.mdblist_tracked_list import MDBListTrackedList  # noqa: F401
from models.mdblist_sync_log import MDBListSyncLog  # noqa: F401
