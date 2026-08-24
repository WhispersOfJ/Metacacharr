#!/usr/bin/env python3
"""Reconcile what Radarr/Sonarr think they have against what Plex actually serves.

Matching is by absolute file path. Both sides use the same /data/<library>/...
paths through the same mount, so path equality is exact where title matching
would produce false pairs across editions and releases.

WHY THIS READS THE API AND NOT THE DATABASE
-------------------------------------------
The first version of this script asked Plex's SQLite DB whether every
metadata_items row for a path was `deleted_at`-flagged, and called the path
invisible if so. That is wrong, and it produced a confident 75-item false
positive on 2026-08-13.

The reason is multi-version episodes. Frieren S02E01 has both a BluRay and a
WEB-DL file attached to the same episode. Plex keeps superseded metadata_items
rows that still reference a file path, while the live episode serves that same
file through a different row. Grouping by path and checking deleted_at cannot
tell those apart, so every second version looked orphaned. All 75 were playable
the whole time.

`/library/sections/<id>/all` (movies) and `/allLeaves` (episodes) return every
Part Plex will actually serve. That is the same thing a user sees, so it is the
only defensible definition of "in Plex". Nothing here reads deleted_at.

Buckets:
  MISSING_FROM_PLEX - Arr has the file, the file is on disk, Plex does not
                      serve it. Genuine gap. Fix: scan, or fix the naming Plex
                      cannot match (a file spanning several episodes will never
                      match, no matter how often you scan).
  FILE_GONE         - Arr believes it has a file, the file is not on disk.
                      An Arr-side problem, not a Plex one.
  UNSUPPORTED       - Plex has no demuxer for the container (.iso, .img, disc
                      images). Absent by design; scanning cannot help.
  ORPHAN_IN_PLEX    - Plex lists it, the file is on disk, no Arr app tracks
                      the path. Usually a manual import, or a series removed
                      from Sonarr whose files stayed.
  STALE_IN_PLEX     - Plex lists it and the file is gone. Not damage: this
                      stack disables autoEmptyTrash on purpose, so removed
                      items linger in the library until trash is emptied.
                      Bulk listings do not carry Plex's accessible/exists
                      attributes - they are always absent on /allLeaves - so
                      the only way to tell these from real orphans is to stat
                      the file. Skipping that check reported 1,238 phantom
                      orphans on 2026-08-13.

The on-disk check runs inside the plex container, because the question is
whether Plex's own FUSE handle can see the file - checking from the host can
pass while Plex's view fails.

Usage:
    plex-arr-reconcile.py [--json] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

# prefix -> (label, plex section id, endpoint)
# Movies list their Parts under /all; shows only expose per-episode Parts under
# /allLeaves, since /all stops at the series level.
LIBRARIES = {
    "/data/movies/": ("Movies", 1, "all"),
    "/data/anime-movies/": ("Anime Movies", 6, "all"),
    "/data/shows/": ("Shows", 2, "allLeaves"),
    "/data/anime-shows/": ("Anime Shows", 7, "allLeaves"),
}

ARR_INSTANCES = [
    ("radarr", 7878, "RADARR_API_KEY", "movie"),
    ("sonarr", 8989, "SONARR_API_KEY", "series"),
]

# Plex has no demuxer for a disc image. Radarr tracks them as movie files, so
# they read as a permanent scan failure unless separated out.
UNSUPPORTED_SUFFIXES = (".iso", ".img", ".mk3d", ".bin", ".nrg")

BUCKETS = ("missing_from_plex", "file_gone", "unsupported",
           "orphan_in_plex", "stale_in_plex")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def arr_paths(env: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Every file path the Arr apps believe is on disk -> which app owns it."""
    owned: dict[str, str] = {}
    problems: list[str] = []

    def get(port: int, path: str, key: str):
        req = urllib.request.Request(f"http://localhost:{port}/api/v3/{path}",
                                     headers={"X-Api-Key": key})
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.load(resp)

    for label, port, env_key, kind in ARR_INSTANCES:
        key = env.get(env_key, "")
        if not key:
            problems.append(f"{label}: no {env_key} in .env")
            continue
        try:
            if kind == "movie":
                for movie in get(port, "movie", key):
                    path = (movie.get("movieFile") or {}).get("path")
                    if movie.get("hasFile") and path:
                        owned[path] = label
            else:
                for series in get(port, "series", key):
                    for ep in get(port, f"episodefile?seriesId={series['id']}", key):
                        if ep.get("path"):
                            owned[ep["path"]] = label
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            problems.append(f"{label}: {exc}")
    return owned, problems


def plex_served(env: dict[str, str]) -> tuple[set[str], list[str]]:
    """Every file path Plex will actually serve, straight from the API."""
    base = env.get("PLEX_URL") or "http://192.168.4.20:32400"
    token = env.get("PLEX_TOKEN", "")
    served: set[str] = set()
    problems: list[str] = []
    if not token:
        return served, ["no PLEX_TOKEN in .env"]
    for _, section, endpoint in LIBRARIES.values():
        url = f"{base.rstrip('/')}/library/sections/{section}/{endpoint}"
        try:
            req = urllib.request.Request(url, headers={"X-Plex-Token": token})
            with urllib.request.urlopen(req, timeout=600) as resp:
                root = ET.fromstring(resp.read())
            served |= {p.get("file") for p in root.iter("Part") if p.get("file")}
        except (urllib.error.URLError, OSError, ET.ParseError) as exc:
            problems.append(f"plex section {section}: {exc}")
    return served, problems


def exists_in_plex_container(paths: list[str]) -> set[str]:
    """Which paths exist, checked from inside the plex container.

    One docker exec for the whole batch: a separate exec per path would take
    minutes and hammer the mount.
    """
    if not paths:
        return set()
    script = 'while IFS= read -r f; do [ -e "$f" ] && printf "%s\\n" "$f"; done'
    result = subprocess.run(
        ["docker", "exec", "-i", "plex", "sh", "-c", script],
        input="\n".join(paths), capture_output=True, text=True, timeout=1800,
    )
    return {line for line in result.stdout.splitlines() if line}


def library_of(path: str) -> str | None:
    for prefix, (label, _, _) in LIBRARIES.items():
        if path.startswith(prefix):
            return label
    return None


def classify(path: str, *, served: bool, on_disk: bool) -> str:
    """Which bucket a single Arr-owned path falls into.

    Pure, so the interesting decision is testable without a running Plex or a
    mounted library. `served` comes from the API and means "Plex will play
    this" - it is deliberately not derived from any deleted_at flag.
    """
    if served:
        return "ok"
    if not on_disk:
        return "file_gone"
    if path.lower().endswith(UNSUPPORTED_SUFFIXES):
        return "unsupported"
    return "missing_from_plex"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    env = load_env()
    arr, problems = arr_paths(env)
    served, plex_problems = plex_served(env)
    problems += plex_problems

    report = {label: {"arr": 0, "plex": 0, **{b: [] for b in BUCKETS}}
              for label, _, _ in LIBRARIES.values()}

    # One existence sweep covers both questions: whether an Arr file Plex does
    # not list is really there, and whether a path Plex lists but no Arr app
    # owns is really there.
    unserved = [p for p in arr if library_of(p) and p not in served]
    unowned = [p for p in served if library_of(p) and p not in arr]
    on_disk = exists_in_plex_container(sorted(set(unserved) | set(unowned)))

    for path in arr:
        label = library_of(path)
        if label is None:
            continue
        report[label]["arr"] += 1
        if path in served:
            continue
        report[label][classify(path, served=False,
                               on_disk=path in on_disk)].append(path)

    for path in served:
        label = library_of(path)
        if label is None:
            continue
        report[label]["plex"] += 1
        if path not in arr:
            report[label]["orphan_in_plex" if path in on_disk
                          else "stale_in_plex"].append(path)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    for problem in problems:
        print(f"  WARNING  {problem}")
    if problems:
        print()

    header = (f"{'Library':<14}{'Arr':>8}{'Plex':>8}{'Missing':>9}"
              f"{'FileGone':>10}{'Unsup':>7}{'Orphan':>8}{'Stale':>7}")
    print(header)
    print("─" * len(header))
    totals = [0] * 7
    for label, _, _ in LIBRARIES.values():
        r = report[label]
        counts = [r["arr"], r["plex"]] + [len(r[b]) for b in BUCKETS]
        totals = [t + c for t, c in zip(totals, counts)]
        print(f"{label:<14}{counts[0]:>8}{counts[1]:>8}{counts[2]:>9}"
              f"{counts[3]:>10}{counts[4]:>7}{counts[5]:>8}{counts[6]:>7}")
    print("─" * len(header))
    print(f"{'TOTAL':<14}{totals[0]:>8}{totals[1]:>8}{totals[2]:>9}"
          f"{totals[3]:>10}{totals[4]:>7}{totals[5]:>8}{totals[6]:>7}")

    for bucket, headline in (
        ("missing_from_plex", "ACTIONABLE - on disk, Arr has it, Plex does not serve it"),
        ("file_gone", "ACTIONABLE - Arr thinks it has a file that is not on disk"),
        ("unsupported", "Not actionable - container Plex cannot index"),
        ("orphan_in_plex", "In Plex and on disk, tracked by no Arr app"),
    ):
        paths = [p for label in report for p in report[label][bucket]]
        if not paths:
            continue
        print(f"\n=== {headline}: {len(paths)} ===")
        for path in sorted(paths)[:args.limit]:
            print(f"  {path}")
        if len(paths) > args.limit:
            print(f"  ... and {len(paths) - args.limit} more")

    if totals[6]:
        print(f"\n{totals[6]} stale rows suppressed (Plex still lists them, file "
              "is gone, autoEmptyTrash disabled on purpose - not damage).")
    print("\nNote: Plex counts can exceed Arr counts. A multi-version episode "
          "(BluRay + WEB-DL) is one file in Sonarr and two Parts in Plex.")

    return 1 if totals[2] + totals[3] else 0


if __name__ == "__main__":
    raise SystemExit(main())
