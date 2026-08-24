#!/usr/bin/env python3
"""Backup / restore / replicate Arr-stack app configuration via their REST APIs.

Usage:
    sync.py backup <app> --out DIR
    sync.py restore <app> <backup.json> --section SECTION [--apply]
    sync.py diff <app> <backup.json>
    sync.py add-root-folder --path PATH --apps app [app...]
    sync.py list-apps
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

APPS = {
    "radarr": {"port": 7878, "api": "v3"},
    "sonarr": {"port": 8989, "api": "v3"},
    "prowlarr": {"port": 9696, "api": "v1"},
}

SECTIONS = ["rootfolder", "downloadclient", "indexer", "notification", "qualityprofile"]

# rootfolder objects have no "name" field (Radarr/Sonarr API) - key on "path" instead.
SECTION_KEY = {"rootfolder": "path"}


class AppConfig:
    def __init__(self, name: str):
        if name not in APPS:
            raise ValueError(f"unknown app '{name}', expected one of {list(APPS)}")
        self.name = name
        meta = APPS[name]
        env_prefix = name.upper()
        default_url = f"http://localhost:{meta['port']}"
        self.base_url = os.environ.get(f"{env_prefix}_URL", default_url).rstrip("/")
        self.api_key = os.environ.get(f"{env_prefix}_API_KEY")
        self.api_version = meta["api"]
        if not self.api_key:
            raise RuntimeError(f"{env_prefix}_API_KEY is not set in the environment")

    def request(self, method: str, path: str, body: dict | None = None) -> object:
        url = f"{self.base_url}/api/{self.api_version}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Api-Key", self.api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {e.read().decode(errors='replace')}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"{method} {url} -> unreachable: {e.reason}") from e


def cmd_list_apps() -> None:
    for name in APPS:
        try:
            app = AppConfig(name)
            status = app.request("GET", "/system/status")
            version = status.get("version", "?") if isinstance(status, dict) else "?"
            print(f"{name}: reachable at {app.base_url} (version {version})")
        except RuntimeError as e:
            print(f"{name}: NOT reachable ({e})")


def cmd_backup(app_name: str, out_dir: Path) -> None:
    app = AppConfig(app_name)
    snapshot = {}
    for section in SECTIONS:
        endpoint = f"/{section}"
        try:
            snapshot[section] = app.request("GET", endpoint)
        except RuntimeError as e:
            print(f"warning: could not fetch {section}: {e}", file=sys.stderr)
            snapshot[section] = None
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    out_file = out_dir / f"{app_name}-{ts}.json"
    out_file.write_text(json.dumps(snapshot, indent=2))
    print(f"wrote backup to {out_file}")


def _index_by_key(items: list[dict], key: str) -> dict:
    return {item.get(key): item for item in items if isinstance(item, dict)}


def cmd_diff(app_name: str, backup_file: Path) -> None:
    app = AppConfig(app_name)
    old = json.loads(backup_file.read_text())
    for section in SECTIONS:
        old_items = old.get(section) or []
        if not isinstance(old_items, list):
            continue
        try:
            new_items = app.request("GET", f"/{section}") or []
        except RuntimeError as e:
            print(f"[{section}] could not fetch current state: {e}")
            continue
        key = SECTION_KEY.get(section, "name")
        old_by_key = _index_by_key(old_items, key)
        new_by_key = _index_by_key(new_items, key)
        added = set(new_by_key) - set(old_by_key)
        removed = set(old_by_key) - set(new_by_key)
        if added or removed:
            print(f"[{section}] added: {sorted(added)} removed: {sorted(removed)}")
        else:
            print(f"[{section}] no {key}-level changes")


def cmd_restore(app_name: str, backup_file: Path, section: str, apply: bool) -> None:
    if section not in SECTIONS:
        raise ValueError(f"unknown section '{section}', expected one of {SECTIONS}")
    app = AppConfig(app_name)
    backup = json.loads(backup_file.read_text())
    backed_up_items = backup.get(section) or []
    if not isinstance(backed_up_items, list):
        print(f"nothing to restore for section '{section}'")
        return
    key = SECTION_KEY.get(section, "name")
    current_items = app.request("GET", f"/{section}") or []
    current_by_key = _index_by_key(current_items, key)

    to_create, to_update = [], []
    for item in backed_up_items:
        item_key = item.get(key)
        if item_key in current_by_key:
            if item != current_by_key[item_key]:
                to_update.append((current_by_key[item_key]["id"], item))
        else:
            to_create.append(item)

    print(f"[{section}] would create {len(to_create)}, update {len(to_update)}")
    for item in to_create:
        print(f"  + create: {item.get(key)}")
    for item_id, item in to_update:
        print(f"  ~ update id={item_id}: {item.get(key)}")

    if not apply:
        print("(dry run — pass --apply to actually write these changes)")
        return

    for item in to_create:
        payload = {k: v for k, v in item.items() if k != "id"}
        app.request("POST", f"/{section}", payload)
    for item_id, item in to_update:
        payload = dict(item)
        payload["id"] = item_id
        app.request("PUT", f"/{section}/{item_id}", payload)
    print("restore applied.")


def cmd_add_root_folder(path: str, app_names: list[str]) -> None:
    for name in app_names:
        app = AppConfig(name)
        existing = app.request("GET", "/rootfolder") or []
        if any(rf.get("path") == path for rf in existing):
            print(f"{name}: root folder {path} already present, skipping")
            continue
        app.request("POST", "/rootfolder", {"path": path})
        print(f"{name}: added root folder {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    p_backup = sub.add_parser("backup")
    p_backup.add_argument("app")
    p_backup.add_argument("--out", type=Path, required=True)

    p_restore = sub.add_parser("restore")
    p_restore.add_argument("app")
    p_restore.add_argument("backup_file", type=Path)
    p_restore.add_argument("--section", required=True, choices=SECTIONS)
    p_restore.add_argument("--apply", action="store_true")

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("app")
    p_diff.add_argument("backup_file", type=Path)

    p_root = sub.add_parser("add-root-folder")
    p_root.add_argument("--path", required=True)
    p_root.add_argument("--apps", nargs="+", required=True, choices=list(APPS))

    sub.add_parser("list-apps")

    args = parser.parse_args()

    try:
        if args.action == "backup":
            cmd_backup(args.app, args.out)
        elif args.action == "restore":
            cmd_restore(args.app, args.backup_file, args.section, args.apply)
        elif args.action == "diff":
            cmd_diff(args.app, args.backup_file)
        elif args.action == "add-root-folder":
            cmd_add_root_folder(args.path, args.apps)
        elif args.action == "list-apps":
            cmd_list_apps()
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
