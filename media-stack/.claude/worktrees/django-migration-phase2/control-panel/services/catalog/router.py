"""Curated software catalog: install/remove/list for the 43 vetted
programs in registry.py. Phase 02 of the control-panel v3 design
treatment - see registry.py's module docstring for why this goes
through the Docker SDK directly instead of writing docker-compose.yml.

Auth: GET routes (list/status) accept current_user_or_service so the
catalog grid can render without a session hiccup the same way other
read-only panels do. install/remove are manual UI actions with no
automation caller, so they require current_user - the same split
services/arr/router.py documents at its own top.
"""
import docker
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.docker_client import docker_client
from core.responses import fail, ok
from core.security import current_user, current_user_or_service
from services.catalog.registry import CATALOG, CATALOG_BY_ID, CATALOG_LABEL, NETWORK

router = APIRouter(tags=["catalog"])

SERVICE_META = {"label": "Software Catalog", "health_check": None}


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


@router.get("/api/catalog")
def catalog_list(_=Depends(current_user_or_service)):
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
    return ok(f"{len(items)} catalog entries, {sum(1 for i in items if i['status'] != 'not_installed')} installed.",
              items=items)


@router.get("/api/catalog/{catalog_id}/status")
def catalog_status(catalog_id: str, _=Depends(current_user_or_service)):
    entry = CATALOG_BY_ID.get(catalog_id)
    if entry is None:
        fail(f"Unknown catalog entry '{catalog_id}'.", status_code=404)
    c = _find_container(catalog_id)
    if c is None:
        return ok("Not installed.", status="not_installed")
    c.reload()
    health = (c.attrs.get("State", {}).get("Health") or {}).get("Status")
    return ok(f"{entry['name']}: {c.status}.", status=c.status, health=health,
              started_at=c.attrs.get("State", {}).get("StartedAt"))


class InstallRequest(BaseModel):
    confirm: bool = False


@router.post("/api/catalog/{catalog_id}/install")
def catalog_install(catalog_id: str, payload: InstallRequest, _=Depends(current_user)):
    entry = CATALOG_BY_ID.get(catalog_id)
    if entry is None:
        fail(f"Unknown catalog entry '{catalog_id}'.", status_code=404)
    if not payload.confirm:
        fail("Set confirm=true to install - this pulls an image and starts a real container.", status_code=400)

    name = _container_name(catalog_id)
    if _find_container(catalog_id) is not None:
        fail(f"{entry['name']} is already installed.", status_code=409)

    wanted_ports = set(entry["ports"].values())
    conflict = wanted_ports & _host_ports_in_use()
    if conflict:
        fail(f"Port(s) {sorted(conflict)} already in use by another container - "
             f"{entry['name']} needs {sorted(wanted_ports)}.", status_code=409)

    image_ref = f"{entry['image']}:{entry['tag']}"
    try:
        docker_client.images.pull(entry["image"], tag=entry["tag"])
    except docker.errors.APIError as e:
        fail(f"Failed to pull {image_ref}: {e}")

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
        fail(f"{entry['name']} failed to start: {e}")

    message = f"{entry['name']} installed and starting."
    if entry.get("caveat"):
        message += f" Note: {entry['caveat']}"
    return ok(message, ports=sorted(wanted_ports))


class RemoveRequest(BaseModel):
    confirm: bool = False
    remove_volumes: bool = False


@router.post("/api/catalog/{catalog_id}/remove")
def catalog_remove(catalog_id: str, payload: RemoveRequest, _=Depends(current_user)):
    entry = CATALOG_BY_ID.get(catalog_id)
    if entry is None:
        fail(f"Unknown catalog entry '{catalog_id}'.", status_code=404)
    if not payload.confirm:
        fail("Set confirm=true to remove.", status_code=400)

    c = _find_container(catalog_id)
    if c is None:
        fail(f"{entry['name']} isn't installed.", status_code=404)

    try:
        c.stop(timeout=15)
        c.remove(v=False)
    except docker.errors.APIError as e:
        fail(f"Failed to remove {entry['name']}: {e}")

    volume_note = ""
    if payload.remove_volumes and entry["volumes"]:
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

    return ok(f"{entry['name']} removed.{volume_note}")
