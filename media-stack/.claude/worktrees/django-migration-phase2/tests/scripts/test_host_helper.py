"""Validation for scripts/host-helper/helper.py - the host-side
privileged-action daemon from .claude/plans/host-privileged-helper.plan.md
(Option B). This IS the security boundary (fixed verb table, no shell,
no caller-supplied argv) - tests exist to lock that shape down, not just
document it.
"""
import importlib.util
import socket
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HELPER_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "host-helper" / "helper.py"


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location("_host_helper", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(returncode=0, stdout="ok", stderr=""):
    return subprocess.CompletedProcess(args=["x"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_verb_table_has_no_shell_true_and_only_literal_argv(helper):
    """The whole security model rests on every verb being a fixed,
    literal argv list - this is the one invariant that must never break."""
    for action, (argv, timeout) in helper.VERBS.items():
        assert isinstance(argv, list) and all(isinstance(part, str) for part in argv), action
        assert isinstance(timeout, (int, float)) and timeout > 0, action


def test_unknown_action_is_rejected_without_running_anything(helper, monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(subprocess, "run", run)
    result = helper._run_verb("rm -rf /")
    assert result["ok"] is False
    assert "Unknown action" in result["message"]
    run.assert_not_called()


def test_reboot_maps_to_systemctl_reboot(helper, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = helper._run_verb("reboot")
    assert captured["argv"] == ["systemctl", "reboot"]
    assert result["ok"] is True


def test_pacman_sync_never_writes_packages(helper, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    helper._run_verb("pacman_sync")
    assert captured["argv"] == ["pacman", "-Sy", "--noconfirm"]


def test_pacman_upgrade_argv(helper, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    helper._run_verb("pacman_upgrade")
    assert captured["argv"] == ["pacman", "-Syu", "--noconfirm"]


def test_run_verb_reports_failure_on_nonzero_exit(helper, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(returncode=1, stdout="", stderr="boom"))
    result = helper._run_verb("reboot")
    assert result["ok"] is False
    assert result["returncode"] == 1
    assert "boom" in result["message"]


def test_run_verb_handles_timeout(helper, monkeypatch):
    def raise_timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    result = helper._run_verb("pacman_upgrade")
    assert result["ok"] is False
    assert "timed out" in result["message"]


def test_handle_request_rejects_malformed_json(helper):
    response, action = helper.handle_request("not json")
    assert response["ok"] is False
    assert action is None


def test_handle_request_rejects_non_object_json(helper):
    response, action = helper.handle_request("[1, 2, 3]")
    assert response["ok"] is False
    assert action is None


def test_handle_request_rejects_missing_action(helper):
    response, action = helper.handle_request("{}")
    assert response["ok"] is False
    assert action is None


def test_handle_request_dispatches_known_verb(helper, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed())
    response, action = helper.handle_request('{"action": "pacman_sync"}')
    assert action == "pacman_sync"
    assert response["ok"] is True


def test_serve_one_end_to_end_over_a_real_socket(helper, monkeypatch, tmp_path):
    """Full protocol round-trip over a real AF_UNIX socket pair - proves
    the newline-framing and JSON envelope actually work together, not
    just each piece in isolation."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(stdout="synced"))
    server_sock, client_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        t = threading.Thread(target=helper.serve_one, args=(server_sock,), daemon=True)
        t.start()
        client_sock.sendall(b'{"action": "pacman_sync"}\n')
        client_sock.shutdown(socket.SHUT_WR)
        data = b""
        while True:
            chunk = client_sock.recv(4096)
            if not chunk:
                break
            data += chunk
        t.join(timeout=2)
    finally:
        client_sock.close()

    import json
    response = json.loads(data.decode())
    assert response["ok"] is True
    assert response["message"] == "synced"


def test_recv_request_rejects_oversized_payload(helper):
    server_sock, client_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client_sock.sendall(b'{"action": "' + b"a" * 5000 + b'"}\n')
        client_sock.close()
        with pytest.raises(ValueError):
            helper._recv_request(server_sock)
    finally:
        server_sock.close()
