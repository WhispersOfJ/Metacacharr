import json
from unittest.mock import patch

import pytest

from core.api_base import ServiceError

LIST_URL = "/api/v2/catalog/"
STATUS_URL = "/api/v2/catalog/uptime-kuma/status"
INSTALL_URL = "/api/v2/catalog/uptime-kuma/install"
REMOVE_URL = "/api/v2/catalog/uptime-kuma/remove"


@pytest.mark.django_db
class TestCatalogListView:
    def test_happy_path(self, authed_client):
        with patch(
            "catalog.api.views.services.list_catalog",
            return_value={"message": "42 catalog entries, 3 installed.", "items": [{"id": "uptime-kuma"}]},
        ):
            response = authed_client.get(LIST_URL)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["ok"] is True
        assert data["items"] == [{"id": "uptime-kuma"}]

    def test_service_client_gets_200(self, service_client):
        """list_catalog is read-only, so a service (API-key) client can also call it."""
        with patch(
            "catalog.api.views.services.list_catalog",
            return_value={"message": "42 catalog entries, 0 installed.", "items": []},
        ):
            response = service_client.get(LIST_URL)

        assert response.status_code == 200

    def test_unauthenticated_gets_401_or_403(self):
        from rest_framework.test import APIClient

        response = APIClient().get(LIST_URL)
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestCatalogStatusView:
    def test_happy_path(self, authed_client):
        with patch(
            "catalog.api.views.services.get_status",
            return_value={"message": "Not installed.", "status": "not_installed"},
        ):
            response = authed_client.get(STATUS_URL)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["ok"] is True
        assert data["status"] == "not_installed"

    def test_unknown_id_returns_404(self, authed_client):
        with patch(
            "catalog.api.views.services.get_status",
            side_effect=ServiceError("Unknown catalog entry 'nope'.", status=404),
        ):
            response = authed_client.get("/api/v2/catalog/nope/status")

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["ok"] is False

    def test_service_client_gets_200(self, service_client):
        with patch(
            "catalog.api.views.services.get_status",
            return_value={"message": "Not installed.", "status": "not_installed"},
        ):
            response = service_client.get(STATUS_URL)

        assert response.status_code == 200


@pytest.mark.django_db
class TestCatalogInstallView:
    def test_happy_path(self, authed_client):
        with patch(
            "catalog.api.views.services.install",
            return_value={"message": "Uptime Kuma installed and starting.", "ports": [3050]},
        ) as mock_install:
            response = authed_client.post(
                INSTALL_URL,
                json.dumps({"confirm": True}),
                content_type="application/json",
                HTTP_HOST="localhost",
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["ok"] is True
        assert data["ports"] == [3050]
        mock_install.assert_called_once_with("uptime-kuma")

    def test_missing_confirm_returns_400_without_calling_service(self, authed_client):
        with patch("catalog.api.views.services.install") as mock_install:
            response = authed_client.post(
                INSTALL_URL,
                json.dumps({}),
                content_type="application/json",
                HTTP_HOST="localhost",
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["ok"] is False
        mock_install.assert_not_called()

    def test_unknown_id_returns_404(self, authed_client):
        with patch(
            "catalog.api.views.services.install",
            side_effect=ServiceError("Unknown catalog entry 'nope'.", status=404),
        ):
            response = authed_client.post(
                "/api/v2/catalog/nope/install",
                json.dumps({"confirm": True}),
                content_type="application/json",
                HTTP_HOST="localhost",
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 404

    def test_already_installed_returns_409(self, authed_client):
        with patch(
            "catalog.api.views.services.install",
            side_effect=ServiceError("Uptime Kuma is already installed.", status=409),
        ):
            response = authed_client.post(
                INSTALL_URL,
                json.dumps({"confirm": True}),
                content_type="application/json",
                HTTP_HOST="localhost",
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 409
        data = json.loads(response.content)
        assert data["ok"] is False

    def test_service_client_gets_403(self, service_client):
        """Critical regression test: a service (API-key) client must NEVER be able to
        trigger a real install, even with confirm=true. Session cookie only.

        HTTP_HOST="localhost"/REMOTE_ADDR="127.0.0.1" are passed so this request
        clears VerifySameOriginMiddleware and actually reaches IsAuthenticatedSessionOnly
        - without them Django's test client defaults HTTP_HOST="testserver", which the
        middleware itself rejects with 403 before the view ever runs, producing a false
        positive that doesn't exercise the permission class at all (the Task 4/7 landmine).
        """
        response = service_client.post(
            INSTALL_URL,
            {"confirm": True},
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

        assert response.status_code == 403
        data = json.loads(response.content)
        # This is DRF's default PermissionDenied body ({"detail": ...}), not the
        # {"ok": false, ...} envelope - envelope_exception_handler only rewrites
        # ServiceError, so a permission-class rejection never reaches it.
        assert "detail" in data


@pytest.mark.django_db
class TestCatalogRemoveView:
    def test_happy_path(self, authed_client):
        with patch(
            "catalog.api.views.services.remove",
            return_value={"message": "Uptime Kuma removed."},
        ) as mock_remove:
            response = authed_client.post(
                REMOVE_URL,
                json.dumps({"confirm": True}),
                content_type="application/json",
                HTTP_HOST="localhost",
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["ok"] is True
        mock_remove.assert_called_once_with("uptime-kuma", remove_volumes=False)

    def test_remove_volumes_flag_is_forwarded(self, authed_client):
        with patch(
            "catalog.api.views.services.remove",
            return_value={"message": "Uptime Kuma removed. Removed 1 volume(s)."},
        ) as mock_remove:
            response = authed_client.post(
                REMOVE_URL,
                json.dumps({"confirm": True, "remove_volumes": True}),
                content_type="application/json",
                HTTP_HOST="localhost",
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 200
        mock_remove.assert_called_once_with("uptime-kuma", remove_volumes=True)

    def test_missing_confirm_returns_400_without_calling_service(self, authed_client):
        with patch("catalog.api.views.services.remove") as mock_remove:
            response = authed_client.post(
                REMOVE_URL,
                json.dumps({}),
                content_type="application/json",
                HTTP_HOST="localhost",
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 400
        mock_remove.assert_not_called()

    def test_not_installed_returns_404(self, authed_client):
        with patch(
            "catalog.api.views.services.remove",
            side_effect=ServiceError("Uptime Kuma isn't installed.", status=404),
        ):
            response = authed_client.post(
                REMOVE_URL,
                json.dumps({"confirm": True}),
                content_type="application/json",
                HTTP_HOST="localhost",
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["ok"] is False

    def test_service_client_gets_403(self, service_client):
        """Same regression coverage as install: session-only, real middleware
        pass-through via HTTP_HOST/REMOTE_ADDR so IsAuthenticatedSessionOnly is
        what actually produces the 403, not VerifySameOriginMiddleware."""
        response = service_client.post(
            REMOVE_URL,
            {"confirm": True},
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

        assert response.status_code == 403
        data = json.loads(response.content)
        assert "detail" in data
