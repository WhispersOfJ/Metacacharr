from core.docker_client import (
    CONTAINER_LABELS,
    MOUNT_DEPENDENTS,
    MOUNT_PREREQS,
    MOUNT_PROVIDERS,
    container_label,
    container_stats,
    docker_client,
    find_project_container,
    project_containers,
    wait_for_healthy,
)


def test_docker_client_is_instantiated():
    assert docker_client is not None


def test_container_labels_registry_is_populated():
    assert "radarr" in CONTAINER_LABELS
    assert "control-panel" in CONTAINER_LABELS


def test_mount_ordering_sets_are_populated():
    assert "nzbdav" in MOUNT_PREREQS
    assert "nzbdav_rclone" in MOUNT_PROVIDERS
    assert "plex" in MOUNT_DEPENDENTS


def test_container_label_falls_back_to_raw_name():
    assert container_label("radarr") == "Radarr"
    assert container_label("some-unknown-service") == "some-unknown-service"


def test_functions_are_callable():
    assert callable(container_stats)
    assert callable(find_project_container)
    assert callable(project_containers)
    assert callable(wait_for_healthy)
