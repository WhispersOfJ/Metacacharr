"""Curated software catalog: install/remove/list for the vetted programs
in registry.py. Ported from control-panel/services/catalog/router.py.

Auth split (documented at the view layer, matching the FastAPI-era
router.py docstring): list_catalog/get_status accept a session OR a
service key (IsAuthenticatedOrServiceKey) so the catalog grid can render
without a session hiccup, the same as other read-only panels. install/
remove are manual UI actions with no automation caller, so they require
a real session (IsAuthenticatedSessionOnly) - the same split
radarr/services.py and host_actions/services.py document at their own
top.

The `confirm` gate for install/remove lives in the view layer (matches
host_actions' _ConfirmedActionView pattern) - these functions assume the
caller already confirmed and never see a `confirm` argument.
"""
import docker

from core.api_base import ServiceError
from core.docker_client import docker_client
from catalog.registry import CATALOG, CATALOG_BY_ID, CATALOG_LABEL, NETWORK


def _container_name(catalog_id: str) -> str:
    return f"catalog-{catalog_id}"


def _find_container(catalog_id: str):
    try:
        return docker_client.containers.get(_container_name(catalog_id))
    except docker.errors.NotFound:
        return None


def _host_ports_in_use(exclude_name: str | None = None) -> set[int]:
    used = set()
    for c in docker_client.containers.list(all=True):
        if exclude_name and c.name == exclude_name:
            continue
        bindings = (c.attrs.get("HostConfig") or {}).get("PortBindings") or {}
        for host_binds in bindings.values():
            if not host_binds:
                continue
            for b in host_binds:
                port = b.get("HostPort")
                if port:
                    used.add(int(port))
    return used


def list_catalog() -> dict:
    items = []
    for entry in CATALOG:
        c = _find_container(entry["id"])
        status = "not_installed"
        if c is not None:
            status = "running" if c.status == "running" else c.status
        items.append({
            "id": entry["id"], "name": entry["name"], "category": entry["category"],
            "pitch": entry["pitch"], "image": f"{entry['image']}:{entry['tag']}",
            "footprint": entry["footprint"], "doc_url": entry["doc_url"], "caveat": entry.get("caveat"),
            "ports": sorted(entry["ports"].values()), "status": status,
            "environment": entry["environment"], "volumes": entry["volumes"],
        })
    installed_count = sum(1 for i in items if i["status"] != "not_installed")
    return {
        "message": f"{len(items)} catalog entries, {installed_count} installed.",
        "items": items,
    }


def get_status(catalog_id: str) -> dict:
    entry = CATALOG_BY_ID.get(catalog_id)
    if entry is None:
        raise ServiceError(f"Unknown catalog entry '{catalog_id}'.", status=404)
    c = _find_container(catalog_id)
    if c is None:
        return {"message": "Not installed.", "status": "not_installed"}
    c.reload()
    health = (c.attrs.get("State", {}).get("Health") or {}).get("Status")
    return {
        "message": f"{entry['name']}: {c.status}.",
        "status": c.status,
        "health": health,
        "started_at": c.attrs.get("State", {}).get("StartedAt"),
    }


def install(catalog_id: str) -> dict:
    entry = CATALOG_BY_ID.get(catalog_id)
    if entry is None:
        raise ServiceError(f"Unknown catalog entry '{catalog_id}'.", status=404)

    name = _container_name(catalog_id)
    if _find_container(catalog_id) is not None:
        raise ServiceError(f"{entry['name']} is already installed.", status=409)

    wanted_ports = set(entry["ports"].values())
    conflict = wanted_ports & _host_ports_in_use()
    if conflict:
        raise ServiceError(
            f"Port(s) {sorted(conflict)} already in use by another container - "
            f"{entry['name']} needs {sorted(wanted_ports)}.",
            status=409,
        )

    image_ref = f"{entry['image']}:{entry['tag']}"
    try:
        docker_client.images.pull(entry["image"], tag=entry["tag"])
    except docker.errors.APIError as e:
        raise ServiceError(f"Failed to pull {image_ref}: {e}") from e

    volumes = dict(entry["volumes"])
    if entry.get("docker_sock"):
        mode = "rw" if catalog_id == "portainer" else "ro"
        volumes["/var/run/docker.sock"] = {"bind": "/var/run/docker.sock", "mode": mode}

    try:
        docker_client.containers.run(
            image_ref,
            name=name,
            network=NETWORK,
            ports=entry["ports"],
            volumes=volumes,
            environment=entry["environment"],
            cap_add=entry["cap_add"] or None,
            command=entry.get("command"),
            restart_policy={"Name": "unless-stopped"},
            labels={CATALOG_LABEL: catalog_id},
            detach=True,
        )
    except docker.errors.APIError as e:
        raise ServiceError(f"{entry['name']} failed to start: {e}") from e

    message = f"{entry['name']} installed and starting."
    if entry.get("caveat"):
        message += f" Note: {entry['caveat']}"
    return {"message": message, "ports": sorted(wanted_ports)}


def remove(catalog_id: str, remove_volumes: bool = False) -> dict:
    entry = CATALOG_BY_ID.get(catalog_id)
    if entry is None:
        raise ServiceError(f"Unknown catalog entry '{catalog_id}'.", status=404)

    c = _find_container(catalog_id)
    if c is None:
        raise ServiceError(f"{entry['name']} isn't installed.", status=404)

    try:
        c.stop(timeout=15)
        c.remove(v=False)
    except docker.errors.APIError as e:
        raise ServiceError(f"Failed to remove {entry['name']}: {e}") from e

    volume_note = ""
    if remove_volumes and entry["volumes"]:
        removed, errors = [], []
        for vol_name in entry["volumes"]:
            try:
                docker_client.volumes.get(vol_name).remove()
                removed.append(vol_name)
            except docker.errors.NotFound:
                continue
            except docker.errors.APIError as e:
                errors.append(f"{vol_name}: {e}")
        volume_note = f" Removed {len(removed)} volume(s)."
        if errors:
            volume_note += f" {len(errors)} volume(s) failed to remove: {errors}"
    elif entry["volumes"]:
        volume_note = " Data volume(s) kept - pass remove_volumes=true to delete them too."

    return {"message": f"{entry['name']} removed.{volume_note}"}
