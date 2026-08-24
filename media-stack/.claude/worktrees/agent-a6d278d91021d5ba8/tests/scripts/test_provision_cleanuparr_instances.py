def test_env_get_missing_file(provision_cleanuparr_instances, tmp_path, monkeypatch):
    monkeypatch.setattr(provision_cleanuparr_instances, "STACK_DIR", tmp_path)
    assert provision_cleanuparr_instances.env_get("RADARR_API_KEY") is None


def test_env_get_found_key(provision_cleanuparr_instances, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("RADARR_API_KEY=abc123\nSONARR_API_KEY=def456\n")
    monkeypatch.setattr(provision_cleanuparr_instances, "STACK_DIR", tmp_path)
    assert provision_cleanuparr_instances.env_get("SONARR_API_KEY") == "def456"


def test_provision_instances_records_failure_when_api_key_missing(
    provision_cleanuparr_instances, tmp_path, monkeypatch
):
    monkeypatch.setattr(provision_cleanuparr_instances, "STACK_DIR", tmp_path)
    created, updated, failed = provision_cleanuparr_instances.provision_instances(dry_run=False)
    assert created == []
    assert updated == []
    assert len(failed) == 2
    assert "RADARR_API_KEY missing" in failed[0]
    assert "SONARR_API_KEY missing" in failed[1]


def test_provision_instances_dry_run_reports_created_for_new_instance(
    provision_cleanuparr_instances, tmp_path, monkeypatch
):
    (tmp_path / ".env").write_text("RADARR_API_KEY=abc\nSONARR_API_KEY=def\n")
    monkeypatch.setattr(provision_cleanuparr_instances, "STACK_DIR", tmp_path)
    monkeypatch.setattr(
        provision_cleanuparr_instances, "request", lambda method, path, body=None, timeout=60: {"instances": []}
    )
    created, updated, failed = provision_cleanuparr_instances.provision_instances(dry_run=True)
    assert created == ["Radarr", "Sonarr"]
    assert updated == []
    assert failed == []


def test_provision_instances_dry_run_reports_updated_for_existing_instance(
    provision_cleanuparr_instances, tmp_path, monkeypatch
):
    (tmp_path / ".env").write_text("RADARR_API_KEY=abc\nSONARR_API_KEY=def\n")
    monkeypatch.setattr(provision_cleanuparr_instances, "STACK_DIR", tmp_path)
    monkeypatch.setattr(
        provision_cleanuparr_instances,
        "request",
        lambda method, path, body=None, timeout=60: {
            "instances": [{"id": 1, "name": "Radarr"}, {"id": 2, "name": "Sonarr"}]
        },
    )
    created, updated, failed = provision_cleanuparr_instances.provision_instances(dry_run=True)
    assert created == []
    assert updated == ["Radarr", "Sonarr"]


def test_provision_instances_records_failure_on_connection_test_error(
    provision_cleanuparr_instances, tmp_path, monkeypatch
):
    import urllib.error

    (tmp_path / ".env").write_text("RADARR_API_KEY=abc\nSONARR_API_KEY=def\n")
    monkeypatch.setattr(provision_cleanuparr_instances, "STACK_DIR", tmp_path)

    def fake_request(method, path, body=None, timeout=60):
        if path.endswith("/instances/test"):
            raise urllib.error.HTTPError(path, 500, "server error", {}, None)
        return {"instances": []}

    monkeypatch.setattr(provision_cleanuparr_instances, "request", fake_request)
    created, updated, failed = provision_cleanuparr_instances.provision_instances(dry_run=False)
    assert created == []
    assert len(failed) == 2
    assert "connection test failed (500)" in failed[0]


def test_provision_seeker_enables_global_and_per_instance_settings(
    provision_cleanuparr_instances, monkeypatch
):
    calls = []

    def fake_request(method, path, body=None, timeout=60):
        if method == "GET":
            return {
                "searchEnabled": False,
                "proactiveSearchEnabled": True,
                "instances": [{"instanceName": "Radarr", "enabled": False}],
            }
        calls.append((method, path, body))
        return {}

    monkeypatch.setattr(provision_cleanuparr_instances, "request", fake_request)
    names = provision_cleanuparr_instances.provision_seeker(dry_run=False)

    assert names == ["Radarr"]
    assert len(calls) == 1
    method, path, body = calls[0]
    assert method == "PUT"
    assert path == "seeker"
    assert body["searchEnabled"] is True
    assert body["proactiveSearchEnabled"] is False
    assert body["instances"][0]["enabled"] is True
    assert body["instances"][0]["activeDownloadLimit"] == 3


def test_provision_seeker_returns_empty_list_on_fetch_failure(provision_cleanuparr_instances, monkeypatch):
    import urllib.error

    def fake_request(method, path, body=None, timeout=60):
        raise urllib.error.HTTPError(path, 503, "unavailable", {}, None)

    monkeypatch.setattr(provision_cleanuparr_instances, "request", fake_request)
    assert provision_cleanuparr_instances.provision_seeker(dry_run=False) == []


def test_provision_seeker_dry_run_does_not_put(provision_cleanuparr_instances, monkeypatch):
    calls = []

    def fake_request(method, path, body=None, timeout=60):
        calls.append(method)
        return {"instances": [{"instanceName": "Radarr"}]}

    monkeypatch.setattr(provision_cleanuparr_instances, "request", fake_request)
    names = provision_cleanuparr_instances.provision_seeker(dry_run=True)
    assert names == ["Radarr"]
    assert calls == ["GET"]
