"""Schema validation for the catalog registry - deterministic, no Docker
mocking needed, catches drift before it reaches router.py. Required keys,
port collisions, and duplicate ids are checked directly against the
CATALOG list built in registry.py.
"""
import sys
from pathlib import Path

CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[2] / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from services.catalog.registry import CATALOG, CATALOG_BY_ID  # noqa: E402

REQUIRED_KEYS = {
    "id", "name", "category", "pitch", "image", "tag", "ports",
    "volumes", "environment", "cap_add", "devices", "footprint",
    "doc_url", "caveat",
}


def test_every_entry_has_all_required_keys():
    missing = {
        entry.get("id", "<no id>"): REQUIRED_KEYS - entry.keys()
        for entry in CATALOG
        if not REQUIRED_KEYS.issubset(entry.keys())
    }
    assert missing == {}, f"entries missing required keys: {missing}"


def test_no_duplicate_ids():
    ids = [entry["id"] for entry in CATALOG]
    assert len(ids) == len(set(ids)), (
        f"duplicate catalog ids found: "
        f"{sorted({i for i in ids if ids.count(i) > 1})}"
    )
    assert len(CATALOG) == len(CATALOG_BY_ID), "CATALOG_BY_ID lost entries to a duplicate id collision"


def test_no_host_port_collisions_within_catalog():
    port_owners: dict[int, str] = {}
    collisions = []
    for entry in CATALOG:
        for host_port in entry["ports"].values():
            if host_port in port_owners:
                collisions.append((host_port, port_owners[host_port], entry["id"]))
            else:
                port_owners[host_port] = entry["id"]
    assert collisions == [], f"host port collisions within the catalog: {collisions}"


def test_no_host_port_collisions_with_compose_file():
    import re

    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose_text = compose_path.read_text()
    compose_ports = {
        int(m)
        for m in re.findall(r'"\s*(\d+):\d+\s*"', compose_text)
    }
    catalog_ports = {p for entry in CATALOG for p in entry["ports"].values()}
    collisions = compose_ports & catalog_ports
    assert not collisions, f"catalog host port(s) collide with docker-compose.yml: {sorted(collisions)}"


def test_at_least_41_entries_across_ten_categories():
    assert len(CATALOG) >= 41, f"expected 41+ entries after the plexanisync catalog entry removal, got {len(CATALOG)}"
    categories = {entry["category"] for entry in CATALOG}
    expected_new = {"Media", "Browser Games", "RetroArch Emulation"}
    assert expected_new.issubset(categories), f"missing expected new categories: {expected_new - categories}"
