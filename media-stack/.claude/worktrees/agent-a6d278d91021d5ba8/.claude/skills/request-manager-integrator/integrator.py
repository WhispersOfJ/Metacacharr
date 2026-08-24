#!/usr/bin/env python3
"""Configure and verify seerr (Jellyseerr/Overseerr-family) <-> Radarr/Sonarr connections.

Usage:
    integrator.py list-connections
    integrator.py connect <radarr|sonarr> --root PATH --profile NAME [--name LABEL] [--force]
    integrator.py verify
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ARR_APPS = {
    # "port" is the docker-internal port (what Seerr's payload uses to reach the
    # app over the compose network - same for every app here, since they each
    # listen on their own internal port regardless of host mapping). "host_port"
    # is only the host-fallback default this script's own direct API calls use
    # when the *_URL env var is unset - it differs from "port" wherever the
    # host-published port differs from the container-internal one.
    "radarr": {"port": 7878, "host_port": 7878, "api": "v3", "seerr_kind": "radarr", "hostname": "radarr"},
    "sonarr": {"port": 8989, "host_port": 8989, "api": "v3", "seerr_kind": "sonarr", "hostname": "sonarr"},
}


class Api:
    def __init__(self, base_url: str, api_key: str, api_version: str, header: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_version = api_version
        self.header = header

    def request(self, method: str, path: str, body: dict | None = None) -> object:
        url = f"{self.base_url}/api/{self.api_version}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header(self.header, self.api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {e.read().decode(errors='replace')}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"{method} {url} -> unreachable: {e.reason}") from e


def seerr_api() -> Api:
    base = os.environ.get("SEERR_URL", "http://localhost:5055")
    key = os.environ.get("SEERR_API_KEY")
    if not key:
        raise RuntimeError("SEERR_API_KEY is not set in the environment")
    return Api(base, key, "v1", "X-Api-Key")


def arr_api(app_name: str) -> Api:
    if app_name not in ARR_APPS:
        raise ValueError(f"unknown app '{app_name}', expected one of {list(ARR_APPS)}")
    meta = ARR_APPS[app_name]
    env_prefix = app_name.upper()
    base = os.environ.get(f"{env_prefix}_URL", f"http://localhost:{meta['host_port']}")
    key = os.environ.get(f"{env_prefix}_API_KEY")
    if not key:
        raise RuntimeError(f"{env_prefix}_API_KEY is not set in the environment")
    return Api(base, key, meta["api"], "X-Api-Key")


def cmd_list_connections() -> None:
    seerr = seerr_api()
    for kind, endpoint in (("radarr", "/settings/radarr"), ("sonarr", "/settings/sonarr")):
        servers = seerr.request("GET", endpoint) or []
        print(f"{kind} connections ({len(servers)}):")
        for s in servers:
            print(f"  - {s.get('name')}  hostname={s.get('hostname')}:{s.get('port')}  "
                  f"root={s.get('activeDirectory')}  profile_id={s.get('activeProfileId')}")


def cmd_connect(app_name: str, root: str, profile_name: str, label: str | None, force: bool) -> None:
    meta = ARR_APPS[app_name]
    arr = arr_api(app_name)

    root_folders = arr.request("GET", "/rootfolder") or []
    if not any(rf.get("path") == root for rf in root_folders):
        raise RuntimeError(
            f"{app_name} has no root folder '{root}' — create it first (see arr-config-sync add-root-folder)"
        )

    profiles = arr.request("GET", "/qualityprofile") or []
    profile = next((p for p in profiles if p.get("name") == profile_name), None)
    if profile is None:
        raise RuntimeError(f"{app_name} has no quality profile named '{profile_name}'")

    seerr = seerr_api()
    endpoint = f"/settings/{meta['seerr_kind']}"
    existing = seerr.request("GET", endpoint) or []
    conn_name = label or f"{app_name.capitalize()} ({profile_name})"
    match = next((s for s in existing if s.get("name") == conn_name), None)
    if match and not force:
        raise RuntimeError(f"connection '{conn_name}' already exists in seerr — pass --force to overwrite")

    # NOT derived from the Arr app's configured base_url - that's used for this script's own
    # direct API calls (RADARR_URL/SONARR_URL, often "localhost" when run from the host itself,
    # outside any container), but Seerr calls out to the Arr app from inside its own container
    # on the compose network, where "localhost" resolves to Seerr itself, not Radarr/Sonarr.
    # Confirmed live: reusing base_url's host here created a connection Seerr could never reach.
    # This stack's container_name always matches the compose service key (radarr, sonarr), so
    # the app name itself is the correct docker-internal hostname.
    hostname = meta["hostname"]
    port = meta["port"]

    payload = {
        "name": conn_name,
        "hostname": hostname,
        "port": port,
        "apiKey": arr.api_key,
        "useSsl": False,
        "baseUrl": "",
        "activeDirectory": root,
        "activeProfileId": profile["id"],
        "activeProfileName": profile["name"],
        "is4k": False,
        "isDefault": not existing,
        "tags": [],
        # Seerr's route handlers do zero server-side defaulting (confirmed against
        # seerr's own settings/radarr.js and sonarr.js - req.body is stored as-is) -
        # any field omitted here is simply absent from stored config, not defaulted
        # to False. syncEnabled absent means availabilitySync.js/downloadtracker.js
        # filter this connection out entirely: requests still get sent to the Arr
        # app, but Seerr never learns the item became available and never tracks
        # download progress. Confirmed live: an existing connection created by an
        # earlier version of this script without these fields was silently broken
        # exactly this way.
        "syncEnabled": True,
        "preventSearch": False,
        "tagRequests": False,
    }
    # Seerr's schema diverges here: Radarr connections require
    # minimumAvailability, Sonarr connections require enableSeasonFolders and
    # monitorNewItems instead - confirmed live against each app's own existing
    # connection.
    if meta["seerr_kind"] == "radarr":
        payload["minimumAvailability"] = "released"
    elif meta["seerr_kind"] == "sonarr":
        payload["enableSeasonFolders"] = True
        payload["monitorNewItems"] = "all"

    if match:
        # id is read-only on Seerr's PUT - confirmed live, a 400 if present in the body at all,
        # even matching the same id the URL path already targets.
        seerr.request("PUT", f"{endpoint}/{match['id']}", payload)
        print(f"updated seerr connection: {conn_name}")
    else:
        seerr.request("POST", endpoint, payload)
        print(f"created seerr connection: {conn_name} -> {app_name} ({hostname}:{port}, root={root}, "
              f"profile={profile_name})")


def cmd_verify() -> None:
    seerr = seerr_api()
    any_failure = False
    for kind, endpoint in (("radarr", "/settings/radarr"), ("sonarr", "/settings/sonarr")):
        servers = seerr.request("GET", endpoint) or []
        for s in servers:
            test_payload = {
                "hostname": s.get("hostname"),
                "port": s.get("port"),
                "apiKey": s.get("apiKey"),
                "useSsl": s.get("useSsl", False),
            }
            try:
                seerr.request("POST", f"{endpoint}/test", test_payload)
                print(f"OK    {kind}:{s.get('name')} ({s.get('hostname')}:{s.get('port')})")
            except RuntimeError as e:
                print(f"FAIL  {kind}:{s.get('name')} ({s.get('hostname')}:{s.get('port')}) -> {e}")
                any_failure = True
    if any_failure:
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("list-connections")

    p_connect = sub.add_parser("connect")
    p_connect.add_argument("app", choices=list(ARR_APPS))
    p_connect.add_argument("--root", required=True)
    p_connect.add_argument("--profile", required=True)
    p_connect.add_argument("--name")
    p_connect.add_argument("--force", action="store_true")

    sub.add_parser("verify")

    args = parser.parse_args()

    try:
        if args.action == "list-connections":
            cmd_list_connections()
        elif args.action == "connect":
            cmd_connect(args.app, args.root, args.profile, args.name, args.force)
        elif args.action == "verify":
            cmd_verify()
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
