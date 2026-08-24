#!/usr/bin/env python3
"""Runs a Fanart.tv poster sync (auto mode - applies the top-liked
candidate, no manual review) against one Plex library via Control Panel's
own /api/posters/sync + /api/posters/sync/stream, and blocks until it
reports DONE/ERROR so the systemd unit's exit status is meaningful.

Control Panel owns the actual sync logic (fanart_best_poster_url etc.) -
this script is just a scriptable client of its HTTP API, same relationship
every other scripts/*.py has to the container it drives.

Run by systemd/stack-poster-sync-{movies,shows}.{service,timer} - Movies
3x/day, Shows 1x/day (TV libraries are far smaller and Fanart's TV art is
updated less often).
"""
import json
import sys
import urllib.error
import urllib.request

CONTROL_PANEL_URL = "http://localhost:8420"


def main():
    if len(sys.argv) != 2:
        print("usage: poster-sync-fanart.py <library title>", file=sys.stderr)
        return 1
    library = sys.argv[1]

    body = json.dumps({"library": library, "source": "fanart", "dry_run": False}).encode()
    req = urllib.request.Request(
        f"{CONTROL_PANEL_URL}/api/posters/sync", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(json.load(r).get("message"))
    except urllib.error.HTTPError as e:
        detail = json.load(e).get("detail", {})
        message = detail.get("message", str(e))
        if e.code == 409:
            # Someone's using the dashboard's own poster-dock at the same
            # moment this timer fired - not a fault of this automation,
            # just a scheduling coincidence. Skip quietly rather than
            # failing the systemd unit and paging over it.
            print(f"skipped for '{library}': {message}")
            return 0
        print(f"failed to start sync for '{library}': {message}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"failed to reach Control Panel: {e}", file=sys.stderr)
        return 1

    try:
        with urllib.request.urlopen(f"{CONTROL_PANEL_URL}/api/posters/sync/stream", timeout=3600) as stream:
            for raw in stream:
                line = raw.decode().strip()
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                print(data)
                if data.startswith("DONE "):
                    return 0
                if data.startswith("ERROR "):
                    return 1
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"lost connection to sync stream: {e}", file=sys.stderr)
        return 1

    print("sync stream ended without a DONE/ERROR line", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
