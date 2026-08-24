"""Gate tests for core/logging_config.py - the shared logger backing every
core/responses.py fail() call. First-ever coverage for this module."""
import importlib
import logging
import sys

import pytest


@pytest.fixture
def logging_config_module(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_PANEL_LOG_DIR", str(tmp_path / "logs"))
    sys.modules.pop("core.logging_config", None)
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent / "control-panel"))
    import core.logging_config as module
    importlib.reload(module)
    yield module
    sys.modules.pop("core.logging_config", None)


def test_configure_logging_creates_log_dir_on_first_log_call(logging_config_module):
    assert not logging_config_module.log_dir().exists()
    logging_config_module.logger.error("trigger the lazy file handler")
    assert logging_config_module.log_dir().is_dir()


def test_configure_logging_writes_entries_to_file(logging_config_module):
    logging_config_module.logger.error("test error message")
    for handler in logging_config_module.logger.handlers:
        handler.flush()
    content = logging_config_module.log_file().read_text()
    assert "test error message" in content


def test_configure_logging_is_idempotent_no_duplicate_handlers(logging_config_module):
    handler_count_before = len(logging_config_module.logger.handlers)
    logging_config_module.configure_logging()
    assert len(logging_config_module.logger.handlers) == handler_count_before


def test_logger_name_is_control_panel(logging_config_module):
    assert logging_config_module.logger.name == "control-panel"


def test_fail_logs_error_via_shared_logger(cp_main_app, caplog):
    from fastapi import HTTPException
    import core.responses as responses

    with caplog.at_level(logging.ERROR, logger="control-panel"):
        with pytest.raises(HTTPException):
            responses.fail("something specific broke")
    assert "something specific broke" in caplog.text
