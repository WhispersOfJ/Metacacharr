from unittest.mock import MagicMock, patch

import docker
import pytest

from catalog import services
from core.api_base import ServiceError


def _not_found(*_args, **_kwargs):
    raise docker.errors.NotFound("not found")


class TestListCatalog:
    def test_all_not_installed(self):
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            result = services.list_catalog()

        assert result["message"] == f"{len(result['items'])} catalog entries, 0 installed."
        assert all(item["status"] == "not_installed" for item in result["items"])
        uptime_kuma = next(i for i in result["items"] if i["id"] == "uptime-kuma")
        assert uptime_kuma["image"] == "louislam/uptime-kuma:2"
        assert uptime_kuma["ports"] == [3050]

    def test_one_installed_and_running(self):
        running = MagicMock(status="running")

        def get_side_effect(name):
            if name == "catalog-uptime-kuma":
                return running
            raise _not_found()

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = get_side_effect
            result = services.list_catalog()

        assert "1 installed." in result["message"]
        uptime_kuma = next(i for i in result["items"] if i["id"] == "uptime-kuma")
        assert uptime_kuma["status"] == "running"

    def test_installed_but_not_running_reports_raw_status(self):
        exited = MagicMock(status="exited")

        def get_side_effect(name):
            if name == "catalog-uptime-kuma":
                return exited
            raise _not_found()

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = get_side_effect
            result = services.list_catalog()

        uptime_kuma = next(i for i in result["items"] if i["id"] == "uptime-kuma")
        assert uptime_kuma["status"] == "exited"


class TestGetStatus:
    def test_unknown_id_raises_404(self):
        with pytest.raises(ServiceError) as exc_info:
            services.get_status("not-a-real-entry")
        assert exc_info.value.status_code == 404

    def test_not_installed(self):
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            result = services.get_status("uptime-kuma")

        assert result == {"message": "Not installed.", "status": "not_installed"}

    def test_installed_reports_status_and_health(self):
        container = MagicMock(status="running")
        container.attrs = {
            "State": {"Health": {"Status": "healthy"}, "StartedAt": "2026-08-22T00:00:00Z"}
        }

        def get_side_effect(name):
            if name == "catalog-uptime-kuma":
                return container
            raise _not_found()

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = get_side_effect
            result = services.get_status("uptime-kuma")

        container.reload.assert_called_once()
        assert result["status"] == "running"
        assert result["health"] == "healthy"
        assert result["started_at"] == "2026-08-22T00:00:00Z"


class TestInstall:
    def test_unknown_id_raises_404(self):
        with pytest.raises(ServiceError) as exc_info:
            services.install("not-a-real-entry")
        assert exc_info.value.status_code == 404

    def test_already_installed_raises_409(self):
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.return_value = MagicMock(status="running")
            with pytest.raises(ServiceError) as exc_info:
                services.install("uptime-kuma")

        assert exc_info.value.status_code == 409
        assert "already installed" in str(exc_info.value.detail)

    def test_port_conflict_raises_409_without_pulling(self):
        other = MagicMock(name="other")
        other.name = "some-other-container"
        other.attrs = {"HostConfig": {"PortBindings": {"3001/tcp": [{"HostPort": "3050"}]}}}

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            mock_docker.containers.list.return_value = [other]
            with pytest.raises(ServiceError) as exc_info:
                services.install("uptime-kuma")

        assert exc_info.value.status_code == 409
        mock_docker.images.pull.assert_not_called()

    def test_success_pulls_image_and_runs_container(self):
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            mock_docker.containers.list.return_value = []
            result = services.install("uptime-kuma")

        mock_docker.images.pull.assert_called_once_with("louislam/uptime-kuma", tag="2")
        mock_docker.containers.run.assert_called_once()
        call_kwargs = mock_docker.containers.run.call_args.kwargs
        assert call_kwargs["name"] == "catalog-uptime-kuma"
        assert call_kwargs["network"] == "stacknet"
        assert call_kwargs["labels"] == {"media-stack.catalog": "uptime-kuma"}
        assert result["ports"] == [3050]
        assert "installed and starting" in result["message"]

    def test_docker_sock_entry_mounts_socket_read_only(self):
        """dozzle has docker_sock=True and is not portainer, so the socket
        bind mode must be 'ro' (only 'portainer' gets 'rw')."""
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            mock_docker.containers.list.return_value = []
            services.install("dozzle")

        call_kwargs = mock_docker.containers.run.call_args.kwargs
        assert call_kwargs["volumes"]["/var/run/docker.sock"] == {
            "bind": "/var/run/docker.sock", "mode": "ro"
        }

    def test_entry_caveat_is_appended_to_install_message(self):
        """beszel has a non-None caveat - install's message must include it,
        matching router.py's `if entry.get('caveat'): message += ...`."""
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            mock_docker.containers.list.return_value = []
            result = services.install("beszel")

        assert "Note:" in result["message"]
        assert "agent" in result["message"]

    def test_pull_failure_raises_service_error(self):
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            mock_docker.containers.list.return_value = []
            mock_docker.images.pull.side_effect = docker.errors.APIError("pull boom")

            with pytest.raises(ServiceError) as exc_info:
                services.install("uptime-kuma")

        assert "Failed to pull" in str(exc_info.value.detail)
        mock_docker.containers.run.assert_not_called()

    def test_run_failure_raises_service_error(self):
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            mock_docker.containers.list.return_value = []
            mock_docker.containers.run.side_effect = docker.errors.APIError("run boom")

            with pytest.raises(ServiceError) as exc_info:
                services.install("uptime-kuma")

        assert "failed to start" in str(exc_info.value.detail)


class TestRemove:
    def test_unknown_id_raises_404(self):
        with pytest.raises(ServiceError) as exc_info:
            services.remove("not-a-real-entry")
        assert exc_info.value.status_code == 404

    def test_not_installed_raises_404(self):
        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.side_effect = _not_found
            with pytest.raises(ServiceError) as exc_info:
                services.remove("uptime-kuma")

        assert exc_info.value.status_code == 404
        assert "isn't installed" in str(exc_info.value.detail)

    def test_success_keeps_volumes_by_default(self):
        container = MagicMock()

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.return_value = container
            result = services.remove("uptime-kuma")

        container.stop.assert_called_once_with(timeout=15)
        container.remove.assert_called_once_with(v=False)
        mock_docker.volumes.get.assert_not_called()
        assert "Data volume(s) kept" in result["message"]

    def test_success_removes_volumes_when_requested(self):
        container = MagicMock()
        volume = MagicMock()

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.return_value = container
            mock_docker.volumes.get.return_value = volume
            result = services.remove("uptime-kuma", remove_volumes=True)

        volume.remove.assert_called_once()
        assert "Removed 1 volume(s)." in result["message"]

    def test_no_volumes_entry_has_no_volume_note(self):
        """dozzle has no volumes at all, so neither the 'kept' nor the
        'removed' note is appended - message is just '<name> removed.'"""
        container = MagicMock()

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.return_value = container
            result = services.remove("dozzle")

        assert result["message"] == "Dozzle removed."

    def test_stop_failure_raises_service_error(self):
        container = MagicMock()
        container.stop.side_effect = docker.errors.APIError("stop boom")

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.return_value = container
            with pytest.raises(ServiceError) as exc_info:
                services.remove("uptime-kuma")

        assert "Failed to remove" in str(exc_info.value.detail)

    def test_volume_not_found_is_skipped_silently(self):
        container = MagicMock()

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.return_value = container
            mock_docker.volumes.get.side_effect = docker.errors.NotFound("no such volume")
            result = services.remove("uptime-kuma", remove_volumes=True)

        assert "Removed 0 volume(s)." in result["message"]
        assert "failed to remove" not in result["message"]

    def test_volume_removal_api_error_is_reported_in_message(self):
        container = MagicMock()

        with patch("catalog.services.docker_client") as mock_docker:
            mock_docker.containers.get.return_value = container
            mock_docker.volumes.get.return_value.remove.side_effect = docker.errors.APIError("vol boom")
            result = services.remove("uptime-kuma", remove_volumes=True)

        assert "Removed 0 volume(s)." in result["message"]
        assert "1 volume(s) failed to remove" in result["message"]
