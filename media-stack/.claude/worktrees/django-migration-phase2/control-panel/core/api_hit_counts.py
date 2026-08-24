"""Live per-app outbound API hit counter, ported from app.py's module-level
httpx.request monkeypatch (app.py:160-203) - Phase 3 is the first phase to
make real outbound HTTP calls from the evolved backend, so this must land
now or the dashboard's hit badges silently stay at zero forever after
cutover.

Extensibility note: app.py built its host->label map once from a single
hardcoded dict. The evolved backend has no such central list (each
services/<name>/router.py is self-contained per the plan's auto-discovery
design), so services register their own host/label pairs via
register_host_label() at import time instead.
"""
from collections import Counter
from urllib.parse import urlparse

import httpx

_API_HOST_LABELS: dict[str, str] = {}
API_HIT_COUNTS: Counter = Counter()

_original_request = httpx.request
_patched = False


def register_host_label(url: str, label: str) -> None:
    """Call at router import time for every external host a service talks
    to. Seeds the counter at 0 so the dashboard shows every badge from a
    cold start, not just ones hit at least once (matches app.py's own
    reasoning for pre-seeding API_HIT_COUNTS)."""
    host = urlparse(url).hostname
    if not host:
        return
    _API_HOST_LABELS[host] = label
    API_HIT_COUNTS.setdefault(label, 0)


def _counted_request(method, url, *args, **kwargs):
    host = urlparse(str(url)).hostname
    API_HIT_COUNTS[_API_HOST_LABELS.get(host, host or "unknown")] += 1
    return _original_request(method, url, *args, **kwargs)


def install() -> None:
    """Idempotent - safe to call from multiple services/*/router.py import
    paths without stacking the wrapper deeper each time (a real bug the
    tests/conftest.py cp_app fixture's docstring already warns about for
    app.py's equivalent, non-idempotent version)."""
    global _patched
    if _patched:
        return
    httpx.request = _counted_request
    httpx._api.request = _counted_request
    _patched = True
