import time
from unittest.mock import MagicMock, patch

import docker
import pytest

from core import nzbdav_client, plex_client
from core.api_base import ServiceError
from plex import services


@pytest.fixture(autouse=True)
def _plex_config(monkeypatch):
    """PLEX_URL/PLEX_TOKEN are empty by default in the test environment
    (see core/plex_client.py's module-level os.environ.get()) - patch the
    core.plex_client module attributes directly (not env vars, since
    they're already bound) so every test in this file gets a configured
    Plex."""
    monkeypatch.setattr(plex_client, "PLEX_URL", "http://plex:32400")
    monkeypatch.setattr(plex_client, "PLEX_TOKEN", "test-plex-token")


def _not_found(*_args, **_kwargs):
    raise docker.errors.NotFound("not found")


def _log_info(analysis_active: bool = False, busy_db_errors: int = 0) -> dict:
    return {
        "lines": ["line1", "line2"], "busy_db_errors": busy_db_errors, "recent_busy_db_timestamps": [],
        "analysis_active": analysis_active, "analysis_batches": 0, "analysis_last_seconds": None,
    }


# ---------------------------------------------------------------------
# scan / list_libraries
# ---------------------------------------------------------------------

class TestScan:
    def test_success(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections/all/refresh")
        result = services.scan()
        assert result == {"message": "Scan for new files started across every library."}

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections/all/refresh", status_code=500)
        with pytest.raises(ServiceError):
            services.scan()


class TestListLibraries:
    def test_success(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [
                {"key": "1", "title": "Movies", "type": "movie"},
                {"key": "2", "title": "TV Shows", "type": "show"},
            ]}},
        )
        result = services.list_libraries()
        assert result["items"] == [{"key": "1", "title": "Movies"}, {"key": "2", "title": "TV Shows"}]
        assert "2 Plex librar" in result["message"]

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        with pytest.raises(ServiceError):
            services.list_libraries()


# ---------------------------------------------------------------------
# empty_trash / analyze
# ---------------------------------------------------------------------

class TestEmptyTrash:
    def test_all_libraries(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [
                {"key": "1", "title": "Movies", "type": "movie"},
                {"key": "2", "title": "TV Shows", "type": "show"},
            ]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/emptyTrash", method="PUT")
        httpx_mock.add_response(url="http://plex:32400/library/sections/2/emptyTrash", method="PUT")
        result = services.empty_trash()
        assert result == {"message": "Trash emptied on: Movies, TV Shows."}

    def test_named_library_case_insensitive(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [
                {"key": "1", "title": "Movies", "type": "movie"},
                {"key": "2", "title": "TV Shows", "type": "show"},
            ]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/emptyTrash", method="PUT")
        result = services.empty_trash("movies")
        assert result == {"message": "Trash emptied on: Movies."}

    def test_no_match_raises(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        with pytest.raises(ServiceError):
            services.empty_trash("nonexistent")

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/emptyTrash", method="PUT", status_code=500)
        with pytest.raises(ServiceError):
            services.empty_trash()

    def test_sections_lookup_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        with pytest.raises(ServiceError):
            services.empty_trash()


class TestAnalyze:
    def test_all_libraries(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/analyze", method="PUT")
        result = services.analyze()
        assert result == {"message": "Deep analysis queued for: Movies."}

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/analyze", method="PUT", status_code=500)
        with pytest.raises(ServiceError):
            services.analyze()


# ---------------------------------------------------------------------
# optimize_db / clean_bundles / butler_task
# ---------------------------------------------------------------------

class TestOptimizeDb:
    def test_success(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/butler/OptimizeDatabase", method="POST")
        result = services.optimize_db()
        assert result == {"message": "Database optimization started."}

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/butler/OptimizeDatabase", method="POST", status_code=500)
        with pytest.raises(ServiceError):
            services.optimize_db()


class TestCleanBundles:
    def test_success(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/butler/CleanOldBundles", method="POST")
        result = services.clean_bundles()
        assert result == {"message": "Cleanup of old bundles started."}

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/butler/CleanOldBundles", method="POST", status_code=500)
        with pytest.raises(ServiceError):
            services.clean_bundles()


class TestButlerTask:
    def test_known_task_success(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/butler/RefreshLibraries", method="POST")
        result = services.butler_task("refresh-libraries")
        assert result == {"message": "Butler task started: refresh-libraries."}

    def test_all_documented_tasks_covered(self):
        # The real FastAPI-era PLEX_BUTLER_TASKS table has 20 entries (the
        # plan's Step 2 text says 19 - a plan/source count mismatch; real
        # source wins, see the final report's deviation list).
        assert len(services.PLEX_BUTLER_TASKS) == 20

    def test_unknown_task_raises_400(self):
        with pytest.raises(ServiceError) as exc_info:
            services.butler_task("not-a-real-task")
        assert exc_info.value.status_code == 400

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/butler/BackupDatabase", method="POST", status_code=500)
        with pytest.raises(ServiceError):
            services.butler_task("backup-database")


# ---------------------------------------------------------------------
# get_updates
# ---------------------------------------------------------------------

class TestGetUpdates:
    def test_with_available_update(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/identity", json={"MediaContainer": {"version": "1.40.0"}})
        httpx_mock.add_response(
            url="http://plex:32400/updater/status",
            json={"MediaContainer": {"Release": [{"version": "1.41.0", "added": "2026-08-01"}]}},
        )
        result = services.get_updates()
        assert result["running_version"] == "1.40.0"
        assert result["update_available"] is True
        assert result["releases"] == [{"version": "1.41.0", "added_at": "2026-08-01"}]

    def test_no_update_available(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/identity", json={"MediaContainer": {"version": "1.40.0"}})
        httpx_mock.add_response(url="http://plex:32400/updater/status", json={"MediaContainer": {"Release": []}})
        result = services.get_updates()
        assert result["update_available"] is False

    def test_updater_status_failure_degrades_gracefully(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/identity", json={"MediaContainer": {"version": "1.40.0"}})
        httpx_mock.add_response(url="http://plex:32400/updater/status", status_code=500)
        result = services.get_updates()
        assert result["running_version"] == "1.40.0"
        assert result["releases"] == []

    def test_identity_failure_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/identity", status_code=500)
        with pytest.raises(ServiceError):
            services.get_updates()


# ---------------------------------------------------------------------
# _plex_container_pid / _bounded_exec / _plex_scanner_processes
# ---------------------------------------------------------------------

class TestPlexContainerPid:
    def test_found(self):
        container = MagicMock()
        container.attrs = {"State": {"Pid": 12345}}
        with patch.object(services, "docker_client") as mock_docker:
            mock_docker.containers.get.return_value = container
            assert services._plex_container_pid() == 12345

    def test_not_found(self):
        with patch.object(services, "docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            assert services._plex_container_pid() is None

    def test_no_pid_in_attrs_returns_none(self):
        container = MagicMock()
        container.attrs = {"State": {}}
        with patch.object(services, "docker_client") as mock_docker:
            mock_docker.containers.get.return_value = container
            assert services._plex_container_pid() is None


class TestBoundedExec:
    def test_returns_result_within_timeout(self):
        container = MagicMock()
        container.exec_run.return_value = "result"
        assert services._bounded_exec(container, ["ls"], timeout=2) == "result"

    def test_returns_none_on_timeout(self):
        container = MagicMock()

        def slow_exec(cmd=None):
            time.sleep(0.3)
            return "too-late"

        container.exec_run.side_effect = slow_exec
        assert services._bounded_exec(container, ["ls"], timeout=0.05) is None


class TestPlexScannerProcesses:
    def test_container_not_found_returns_empty(self):
        with patch.object(services, "docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            assert services._plex_scanner_processes() == []

    def test_finds_scanner_lines(self):
        container = MagicMock()
        result = MagicMock()
        result.output = b"root  1  0.0  ps aux\nplex  2  1.0  Plex Media Scanner --scan\n"
        with patch.object(services, "docker_client") as mock_docker, \
                patch.object(services, "_bounded_exec", return_value=result):
            mock_docker.containers.get.return_value = container
            lines = services._plex_scanner_processes()
        assert len(lines) == 1
        assert "Plex Media Scanner" in lines[0]

    def test_bounded_exec_timeout_returns_empty(self):
        container = MagicMock()
        with patch.object(services, "docker_client") as mock_docker, \
                patch.object(services, "_bounded_exec", return_value=None):
            mock_docker.containers.get.return_value = container
            assert services._plex_scanner_processes() == []

    def test_exec_exception_returns_empty(self):
        container = MagicMock()
        with patch.object(services, "docker_client") as mock_docker, \
                patch.object(services, "_bounded_exec", side_effect=RuntimeError("boom")):
            mock_docker.containers.get.return_value = container
            assert services._plex_scanner_processes() == []


# ---------------------------------------------------------------------
# _plex_dstate_threads
# ---------------------------------------------------------------------

class TestPlexDstateThreads:
    def test_no_pid_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(services, "HOST_PROC_DIR", str(tmp_path))
        assert services._plex_dstate_threads(None) == []

    def test_proc_dir_missing_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(services, "HOST_PROC_DIR", str(tmp_path / "does-not-exist"))
        assert services._plex_dstate_threads(123) == []

    def test_no_dstate_threads(self, monkeypatch, tmp_path):
        proc_dir = tmp_path / "proc"
        task_dir = proc_dir / "123" / "task" / "1"
        task_dir.mkdir(parents=True)
        (task_dir / "status").write_text("Name:\tPlexScript\nState:\tS (sleeping)\n")
        monkeypatch.setattr(services, "HOST_PROC_DIR", str(proc_dir))
        assert services._plex_dstate_threads(123) == []

    def test_finds_dstate_thread_with_stack(self, monkeypatch, tmp_path):
        proc_dir = tmp_path / "proc"
        task_dir = proc_dir / "123" / "task" / "7"
        task_dir.mkdir(parents=True)
        (task_dir / "status").write_text("Name:\tfuse-worker\nState:\tD (disk sleep)\n")
        (task_dir / "stack").write_text("[<0>] fuse_wait\n[<0>] request_wait_answer\n")
        monkeypatch.setattr(services, "HOST_PROC_DIR", str(proc_dir))
        result = services._plex_dstate_threads(123)
        assert len(result) == 1
        assert result[0]["tid"] == "7"
        assert result[0]["comm"] == "fuse-worker"
        assert result[0]["state"] == "D (disk sleep)"
        assert result[0]["stack"] == ["[<0>] fuse_wait", "[<0>] request_wait_answer"]

    def test_dstate_thread_without_stack_file(self, monkeypatch, tmp_path):
        proc_dir = tmp_path / "proc"
        task_dir = proc_dir / "123" / "task" / "9"
        task_dir.mkdir(parents=True)
        (task_dir / "status").write_text("Name:\tfuse-worker\nState:\tD (disk sleep)\n")
        monkeypatch.setattr(services, "HOST_PROC_DIR", str(proc_dir))
        result = services._plex_dstate_threads(123)
        assert result[0]["tid"] == "9"
        assert "stack" not in result[0]

    def test_task_dir_missing_returns_empty(self, monkeypatch, tmp_path):
        proc_dir = tmp_path / "proc"
        proc_dir.mkdir()
        monkeypatch.setattr(services, "HOST_PROC_DIR", str(proc_dir))
        assert services._plex_dstate_threads(999) == []


# ---------------------------------------------------------------------
# _fuse_waiting_total
# ---------------------------------------------------------------------

class TestFuseWaitingTotal:
    def test_no_conn_dir_returns_zero(self, monkeypatch, tmp_path):
        monkeypatch.setattr(services, "HOST_SYS_FUSE_DIR", str(tmp_path / "missing"))
        assert services._fuse_waiting_total() == 0

    def test_sums_waiting_counters(self, monkeypatch, tmp_path):
        fuse_dir = tmp_path / "fuse"
        for conn_id, value in [("1", "3"), ("2", "5")]:
            conn_dir = fuse_dir / "connections" / conn_id
            conn_dir.mkdir(parents=True)
            (conn_dir / "waiting").write_text(value)
        monkeypatch.setattr(services, "HOST_SYS_FUSE_DIR", str(fuse_dir))
        assert services._fuse_waiting_total() == 8

    def test_skips_unreadable_or_invalid_entries(self, monkeypatch, tmp_path):
        fuse_dir = tmp_path / "fuse"
        good = fuse_dir / "connections" / "1"
        good.mkdir(parents=True)
        (good / "waiting").write_text("2")
        bad = fuse_dir / "connections" / "2"
        bad.mkdir(parents=True)
        (bad / "waiting").write_text("not-a-number")
        (fuse_dir / "connections" / "3").mkdir(parents=True)  # no waiting file at all
        monkeypatch.setattr(services, "HOST_SYS_FUSE_DIR", str(fuse_dir))
        assert services._fuse_waiting_total() == 2


# ---------------------------------------------------------------------
# _plex_log_tail
# ---------------------------------------------------------------------

class TestPlexLogTail:
    def test_missing_log_file_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
        assert services._plex_log_tail() == {
            "lines": [], "busy_db_errors": 0, "recent_busy_db_timestamps": [],
            "analysis_active": False, "analysis_batches": 0, "analysis_last_seconds": None,
        }

    def test_reads_tail_and_counts_busy_db_and_analysis(self, monkeypatch, tmp_path):
        log_dir = tmp_path / "plex" / "Plex Media Server" / "Logs"
        log_dir.mkdir(parents=True)
        log_path = log_dir / "Plex Media Server.log"
        lines = [
            "[2026-08-23 10:00:00.000] Media Analyzer: Performing on-the-fly analysis for X",
            "[2026-08-23 10:00:05.000] Database :: busy database, retrying",
            "[2026-08-23 10:00:10.000] Media Analyzer: Background analysis completed in 4.2 seconds",
            "[2026-08-23 10:00:11.000] some other unrelated line",
        ]
        log_path.write_text("\n".join(lines) + "\n")
        monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
        result = services._plex_log_tail(lines=10)
        assert result["busy_db_errors"] == 1
        assert result["analysis_active"] is True
        assert result["analysis_batches"] == 2
        assert result["analysis_last_seconds"] == 4.2
        assert len(result["recent_busy_db_timestamps"]) == 1

    def test_only_tails_last_bytes(self, monkeypatch, tmp_path):
        log_dir = tmp_path / "plex" / "Plex Media Server" / "Logs"
        log_dir.mkdir(parents=True)
        log_path = log_dir / "Plex Media Server.log"
        log_path.write_text("old line that should be excluded\n" * 100 + "newest line\n")
        monkeypatch.setattr(services, "HOST_CONFIG_DIR", str(tmp_path))
        result = services._plex_log_tail(lines=1, tail_bytes=50)
        assert result["lines"] == ["newest line"]


# ---------------------------------------------------------------------
# _nzbdav_queue_counts
# ---------------------------------------------------------------------

class TestNzbdavQueueCounts:
    def test_success(self, httpx_mock, monkeypatch):
        monkeypatch.setattr(nzbdav_client, "NZBDAV_API_KEY", "test-key")
        httpx_mock.add_response(
            url="http://nzbdav:3000/api?mode=queue&output=json&apikey=test-key",
            json={"queue": {"slots": [
                {"status": "Downloading"}, {"status": "Downloading"}, {"status": "Queued"},
            ]}},
        )
        result = services._nzbdav_queue_counts()
        assert result == {"pending": 1, "processing": 2}

    def test_unreachable_returns_flag(self, monkeypatch):
        monkeypatch.setattr(nzbdav_client, "NZBDAV_API_KEY", None)
        result = services._nzbdav_queue_counts()
        assert result == {"pending": 0, "processing": 0, "unreachable": True}


# ---------------------------------------------------------------------
# _mount_test
# ---------------------------------------------------------------------

class TestMountTest:
    def test_container_not_found_returns_false(self):
        with patch.object(services, "docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            assert services._mount_test() is False

    def test_success(self):
        container = MagicMock()
        result = MagicMock(exit_code=0)
        with patch.object(services, "docker_client") as mock_docker, \
                patch.object(services, "_bounded_exec", return_value=result):
            mock_docker.containers.get.return_value = container
            assert services._mount_test() is True

    def test_nonzero_exit_returns_false(self):
        container = MagicMock()
        result = MagicMock(exit_code=1)
        with patch.object(services, "docker_client") as mock_docker, \
                patch.object(services, "_bounded_exec", return_value=result):
            mock_docker.containers.get.return_value = container
            assert services._mount_test() is False

    def test_bounded_exec_timeout_returns_false(self):
        container = MagicMock()
        with patch.object(services, "docker_client") as mock_docker, \
                patch.object(services, "_bounded_exec", return_value=None):
            mock_docker.containers.get.return_value = container
            assert services._mount_test() is False

    def test_exec_exception_returns_false(self):
        container = MagicMock()
        with patch.object(services, "docker_client") as mock_docker, \
                patch.object(services, "_bounded_exec", side_effect=RuntimeError("boom")):
            mock_docker.containers.get.return_value = container
            assert services._mount_test() is False


# ---------------------------------------------------------------------
# get_activities / get_progress_snapshot
# ---------------------------------------------------------------------

class TestGetActivities:
    def test_success(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/activities",
            json={"MediaContainer": {"Activity": [{"uuid": "abc", "progress": 42}]}},
        )
        assert services.get_activities() == [{"uuid": "abc", "progress": 42}]

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/activities", status_code=500)
        with pytest.raises(ServiceError):
            services.get_activities()


class TestGetProgressSnapshot:
    def test_success(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/activities",
            json={"MediaContainer": {"Activity": [
                {"uuid": "abc", "progress": 42}, {"uuid": "def", "progress": 10},
            ]}},
        )
        assert services.get_progress_snapshot() == {"abc": 42, "def": 10}

    def test_service_error_returns_empty(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/activities", status_code=500)
        assert services.get_progress_snapshot() == {}


# ---------------------------------------------------------------------
# scan_health
# ---------------------------------------------------------------------

class TestScanHealth:
    def _run(self, *, pid=None, dstate=None, fuse_waiting=0, mount_ok=True, scanner_lines=None,
              nzbdav_queue=None, log_info=None, activities=None, container_found=True,
              container_health="healthy", restart_count=0):
        dstate = [] if dstate is None else dstate
        scanner_lines = [] if scanner_lines is None else scanner_lines
        nzbdav_queue = {"pending": 0, "processing": 0} if nzbdav_queue is None else nzbdav_queue
        log_info = _log_info() if log_info is None else log_info
        activities = [] if activities is None else activities

        with patch.object(services, "_plex_container_pid", return_value=pid), \
                patch.object(services, "_plex_dstate_threads", return_value=dstate), \
                patch.object(services, "_fuse_waiting_total", return_value=fuse_waiting), \
                patch.object(services, "_mount_test", return_value=mount_ok), \
                patch.object(services, "_plex_scanner_processes", return_value=scanner_lines), \
                patch.object(services, "_nzbdav_queue_counts", return_value=nzbdav_queue), \
                patch.object(services, "_plex_log_tail", return_value=log_info), \
                patch.object(services, "get_activities", return_value=activities), \
                patch.object(services, "docker_client") as mock_docker:
            if container_found:
                container = MagicMock()
                container.attrs = {"State": {"Health": {"Status": container_health}}, "RestartCount": restart_count}
                mock_docker.containers.get.return_value = container
            else:
                mock_docker.containers.get.side_effect = _not_found
            return services.scan_health()

    def test_hung_confirmed_dstate(self):
        result = self._run(dstate=[{"tid": "1", "comm": "fuse", "state": "D"}])
        assert result["state"] == "hung_confirmed"

    def test_hung_confirmed_mount_fail(self):
        result = self._run(mount_ok=False)
        assert result["state"] == "hung_confirmed"

    def test_stalled_suspected(self):
        result = self._run(
            nzbdav_queue={"pending": 2, "processing": 0},
            activities=[{"uuid": "a", "progress": 5}],
            scanner_lines=[],
            log_info=_log_info(analysis_active=False),
        )
        assert result["state"] == "stalled_suspected"

    def test_scanning_when_scanner_running(self):
        result = self._run(
            nzbdav_queue={"pending": 2, "processing": 0},
            activities=[{"uuid": "a", "progress": 5}],
            scanner_lines=["Plex Media Scanner running"],
        )
        assert result["state"] == "scanning"

    def test_scanning_no_queue_but_activities(self):
        result = self._run(activities=[{"uuid": "a", "progress": 5}])
        assert result["state"] == "scanning"

    def test_healthy(self):
        result = self._run()
        assert result["state"] == "healthy"
        assert result["message"] == "Plex is healthy."

    def test_container_missing_reports_missing_health(self):
        result = self._run(container_found=False)
        assert result["container"] == {"health": "missing", "restart_count": 0}

    def test_health_missing_reports_unknown(self):
        with patch.object(services, "_plex_container_pid", return_value=None), \
                patch.object(services, "_plex_dstate_threads", return_value=[]), \
                patch.object(services, "_fuse_waiting_total", return_value=0), \
                patch.object(services, "_mount_test", return_value=True), \
                patch.object(services, "_plex_scanner_processes", return_value=[]), \
                patch.object(services, "_nzbdav_queue_counts", return_value={"pending": 0, "processing": 0}), \
                patch.object(services, "_plex_log_tail", return_value=_log_info()), \
                patch.object(services, "get_activities", return_value=[]), \
                patch.object(services, "docker_client") as mock_docker:
            container = MagicMock()
            container.attrs = {"State": {}, "RestartCount": 3}
            mock_docker.containers.get.return_value = container
            result = services.scan_health()
        assert result["container"] == {"health": "unknown", "restart_count": 3}

    def test_activities_lookup_failure_degrades_to_empty(self):
        with patch.object(services, "_plex_container_pid", return_value=None), \
                patch.object(services, "_plex_dstate_threads", return_value=[]), \
                patch.object(services, "_fuse_waiting_total", return_value=0), \
                patch.object(services, "_mount_test", return_value=True), \
                patch.object(services, "_plex_scanner_processes", return_value=[]), \
                patch.object(services, "_nzbdav_queue_counts", return_value={"pending": 0, "processing": 0}), \
                patch.object(services, "_plex_log_tail", return_value=_log_info()), \
                patch.object(services, "get_activities", side_effect=ServiceError("down")), \
                patch.object(services, "docker_client") as mock_docker:
            container = MagicMock()
            container.attrs = {"State": {"Health": {"Status": "healthy"}}, "RestartCount": 0}
            mock_docker.containers.get.return_value = container
            result = services.scan_health()
        assert result["activities"] == []
        assert result["state"] == "healthy"


# ---------------------------------------------------------------------
# duplicates
# ---------------------------------------------------------------------

class TestDuplicates:
    def test_flags_and_skips_singles_and_small_totals(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [
                {"key": "1", "title": "Movies", "type": "movie"},
                {"key": "2", "title": "TV", "type": "show"},
            ]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all",
            json={"MediaContainer": {"Metadata": [
                {
                    "title": "Big Movie", "year": 2020, "ratingKey": "100",
                    "Media": [{"Part": [{"size": 6_000_000_000}]}, {"Part": [{"size": 5_000_000_000}]}],
                },
                {
                    "title": "Small Movie", "year": 2021, "ratingKey": "101",
                    "Media": [{"Part": [{"size": 1_000_000_000}]}],
                },
                {
                    "title": "Not Big Enough", "year": 2019, "ratingKey": "102",
                    "Media": [{"Part": [{"size": 1_000_000_000}]}, {"Part": [{"size": 500_000_000}]}],
                },
            ]}},
        )
        result = services.duplicates(min_gb=5.0)
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Big Movie"
        assert result["items"][0]["file_count"] == 2

    def test_skips_show_sections(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "2", "title": "TV", "type": "show"}]}},
        )
        result = services.duplicates()
        assert result["items"] == []

    def test_section_fetch_error_skipped(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/sections/1/all", status_code=500)
        result = services.duplicates()
        assert result["items"] == []

    def test_sections_lookup_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        with pytest.raises(ServiceError):
            services.duplicates()


# ---------------------------------------------------------------------
# tmdb_missing
# ---------------------------------------------------------------------

class TestTmdbMissing:
    def test_flags_missing_and_skips_present(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?includeGuids=1&X-Plex-Container-Size=200000",
            json={"MediaContainer": {"Metadata": [
                {"title": "Has TMDb", "year": 2020, "ratingKey": "1", "Guid": [{"id": "tmdb://123"}]},
                {"title": "Legacy Agent", "year": 2019, "ratingKey": "2",
                 "guid": "com.plexapp.agents.themoviedb://456"},
                {"title": "Missing Link", "year": 2021, "ratingKey": "3"},
            ]}},
        )
        result = services.tmdb_missing()
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Missing Link"
        assert result["items"][0]["library"] == "Movies"

    def test_skips_non_movie_show_sections(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "3", "title": "Music", "type": "artist"}]}},
        )
        result = services.tmdb_missing()
        assert result["items"] == []

    def test_section_fetch_error_skipped(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/sections",
            json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/sections/1/all?includeGuids=1&X-Plex-Container-Size=200000",
            status_code=500,
        )
        result = services.tmdb_missing()
        assert result["items"] == []

    def test_sections_lookup_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/sections", status_code=500)
        with pytest.raises(ServiceError):
            services.tmdb_missing()


# ---------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------

class TestSessions:
    def test_maps_active_sessions(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/status/sessions",
            json={"MediaContainer": {"Metadata": [
                {
                    "title": "Episode 1", "grandparentTitle": "My Show",
                    "User": {"title": "bear"}, "Player": {"product": "Plex Web", "state": "playing"},
                    "Media": [{"videoDecision": "directplay"}],
                    "viewOffset": 300000, "duration": 600000,
                },
                {
                    "title": "A Movie", "User": {"title": "guest"},
                    "Player": {"product": "Plex for iOS", "state": "buffering"},
                    "Media": [{"selected": True}], "viewOffset": 0, "duration": 0,
                },
            ]}},
        )
        result = services.sessions()
        assert len(result["sessions"]) == 2
        assert result["sessions"][0]["title"] == "My Show - Episode 1"
        assert result["sessions"][0]["decision"] == "directplay"
        assert result["sessions"][0]["progress_pct"] == 50.0
        assert result["sessions"][1]["progress_pct"] == 0.0

    def test_no_active_sessions(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/status/sessions", json={"MediaContainer": {}})
        result = services.sessions()
        assert result == {"message": "0 active session(s).", "sessions": []}

    def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/status/sessions", status_code=500)
        with pytest.raises(ServiceError):
            services.sessions()


# ---------------------------------------------------------------------
# recently_added
# ---------------------------------------------------------------------

class TestRecentlyAdded:
    def test_combines_and_sorts_movies_and_shows(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/all?sort=addedAt%3Adesc&type=1",
            json={"MediaContainer": {"Metadata": [
                {"title": "Movie A", "year": 2020, "type": "movie", "addedAt": 100, "librarySectionTitle": "Movies"},
            ]}},
        )
        httpx_mock.add_response(
            url="http://plex:32400/library/all?sort=addedAt%3Adesc&type=2",
            json={"MediaContainer": {"Metadata": [
                {"title": "Show B", "year": 2021, "type": "show", "addedAt": 200, "librarySectionTitle": "TV"},
            ]}},
        )
        result = services.recently_added(limit=15)
        assert [i["title"] for i in result["items"]] == ["Show B", "Movie A"]

    def test_limit_applied(self, httpx_mock):
        movies = [
            {"title": f"Movie {i}", "year": 2020, "type": "movie", "addedAt": i, "librarySectionTitle": "Movies"}
            for i in range(5)
        ]
        httpx_mock.add_response(url="http://plex:32400/library/all?sort=addedAt%3Adesc&type=1",
                                 json={"MediaContainer": {"Metadata": movies}})
        httpx_mock.add_response(url="http://plex:32400/library/all?sort=addedAt%3Adesc&type=2",
                                 json={"MediaContainer": {"Metadata": []}})
        result = services.recently_added(limit=2)
        assert len(result["items"]) == 2
        assert result["items"][0]["title"] == "Movie 4"

    def test_shows_fetch_failure_degrades_gracefully(self, httpx_mock):
        httpx_mock.add_response(
            url="http://plex:32400/library/all?sort=addedAt%3Adesc&type=1",
            json={"MediaContainer": {"Metadata": [
                {"title": "Movie A", "year": 2020, "type": "movie", "addedAt": 100, "librarySectionTitle": "Movies"},
            ]}},
        )
        httpx_mock.add_response(url="http://plex:32400/library/all?sort=addedAt%3Adesc&type=2", status_code=500)
        result = services.recently_added()
        assert len(result["items"]) == 1

    def test_movies_fetch_failure_raises(self, httpx_mock):
        httpx_mock.add_response(url="http://plex:32400/library/all?sort=addedAt%3Adesc&type=1", status_code=500)
        with pytest.raises(ServiceError):
            services.recently_added()
