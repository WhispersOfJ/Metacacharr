"""Gate tests for core/responses.py (shared ok/fail/now envelope) and
core/host_paths.py (constants). First-ever coverage for either module -
app.py's test_helpers.py tested app.py's own copy, never ported after the
functions moved here."""
import pytest
from fastapi import HTTPException


@pytest.fixture
def responses_module(cp_main_app):
    import core.responses as module
    return module


def test_ok_shape(responses_module):
    result = responses_module.ok("did the thing", extra=1)
    assert result["ok"] is True
    assert result["message"] == "did the thing"
    assert result["extra"] == 1
    assert "time" in result


def test_fail_raises_http_exception_with_default_status(responses_module):
    with pytest.raises(HTTPException) as exc:
        responses_module.fail("something broke")
    assert exc.value.status_code == 502
    assert exc.value.detail["ok"] is False
    assert exc.value.detail["message"] == "something broke"


def test_fail_respects_custom_status_code(responses_module):
    with pytest.raises(HTTPException) as exc:
        responses_module.fail("not found", status_code=404)
    assert exc.value.status_code == 404


def test_now_returns_hh_mm_ss_format(responses_module):
    import re
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", responses_module.now())


def test_host_paths_constants_are_absolute():
    import core.host_paths as hp
    for path in (hp.HOST_CONFIG_DIR, hp.HOST_MNT_DIR, hp.HOST_PROC_DIR, hp.HOST_SYS_FUSE_DIR, hp.HOST_README):
        assert path.startswith("/")
