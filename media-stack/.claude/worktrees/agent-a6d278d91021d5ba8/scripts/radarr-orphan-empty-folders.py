#!/usr/bin/env python3
"""Remove empty movie folders left behind by movies deleted from Radarr.

Background (2026-08-13): `createEmptyMovieFolders=True` (deliberate - see
STACK.md "Sonarr/Radarr silently drop a freshly-added series/movie's first
import") makes Radarr create a destination folder at add-time. When a movie is
later removed from Radarr without ever downloading, that folder is orphaned,
because `deleteEmptyFolders` is off. Turning that setting on is NOT the fix:
it deletes the same folders the create-empty-folders fix depends on, which
reintroduces the hung-ProcessMonitoredDownloads bug.

This script instead removes only folders meeting ALL of:
  1. Radarr itself reports the folder as unmapped, AND
  2. the folder name carries a {tmdb-N} tag whose id is absent from Radarr, AND
  3. the folder is empty at the moment of deletion.

Deletion uses os.rmdir, which fails on a non-empty directory - so a folder
that gains a file between the scan and the delete can never be destroyed.

Usage:
    radarr-orphan-empty-folders.py --dry-run           # default, prints plan
    radarr-orphan-empty-folders.py --apply             # actually deletes
    radarr-orphan-empty-folders.py --apply --snapshot out.json
"""
import argparse
import json
import os
import re
import sys
import urllib.request

DEFAULT_RADARR_URL = "http://localhost:7878"
DEFAULT_HOST_ROOT = "/home/bear/Claude/media-stack/media/movies"
TMDB_TAG = re.compile(r"\{tmdb-(\d+)\}")


def _get(url, api_key, timeout=180):
    req = urllib.request.Request(url, headers={"X-Api-Key": api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch_unmapped_folders(base_url, api_key):
    """Folder names Radarr itself reports as belonging to no movie."""
    roots = _get(f"{base_url}/api/v3/rootfolder", api_key)
    names = []
    for root in roots:
        for entry in root.get("unmappedFolders") or []:
            names.append(os.path.basename(entry["path"]))
    return names


def fetch_known_tmdb_ids(base_url, api_key):
    return {m["tmdbId"] for m in _get(f"{base_url}/api/v3/movie", api_key)}


def classify(names, known_tmdb_ids, host_root):
    """Split candidates into deletable and skipped, with a reason for each skip.

    Anything that is not provably an orphaned *empty* folder is skipped. The
    caller never deletes on a guess.
    """
    deletable, skipped = [], []
    for name in names:
        path = os.path.join(host_root, name)
        match = TMDB_TAG.search(name)
        if not match:
            skipped.append((name, "no tmdb tag in folder name"))
            continue
        if int(match.group(1)) in known_tmdb_ids:
            skipped.append((name, "tmdb id still present in Radarr"))
            continue
        try:
            entries = os.listdir(path)
        except FileNotFoundError:
            skipped.append((name, "folder no longer exists"))
            continue
        except OSError as exc:
            skipped.append((name, f"unreadable: {exc.strerror}"))
            continue
        if entries:
            skipped.append((name, f"not empty ({len(entries)} entries)"))
            continue
        deletable.append(name)
    return deletable, skipped


def delete_folders(names, host_root):
    """rmdir each folder. Non-empty dirs raise OSError and are reported, never forced."""
    removed, failed = [], []
    for name in names:
        try:
            os.rmdir(os.path.join(host_root, name))
            removed.append(name)
        except OSError as exc:
            failed.append((name, exc.strerror))
    return removed, failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually delete (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="explicit no-op mode (default)")
    parser.add_argument("--radarr-url", default=DEFAULT_RADARR_URL)
    parser.add_argument("--host-root", default=DEFAULT_HOST_ROOT)
    parser.add_argument("--api-key", default=os.environ.get("RADARR_API_KEY"))
    parser.add_argument("--snapshot", help="write the full plan to this JSON file before deleting")
    args = parser.parse_args(argv)

    if not args.api_key:
        parser.error("no API key: pass --api-key or set RADARR_API_KEY")

    names = fetch_unmapped_folders(args.radarr_url, args.api_key)
    known = fetch_known_tmdb_ids(args.radarr_url, args.api_key)
    deletable, skipped = classify(names, known, args.host_root)

    print(f"unmapped folders reported by Radarr: {len(names)}")
    print(f"orphaned AND empty (deletable):      {len(deletable)}")
    print(f"skipped:                             {len(skipped)}")
    for name, reason in skipped[:20]:
        print(f"  SKIP {name[:60]} - {reason}")

    if args.snapshot:
        with open(args.snapshot, "w") as fh:
            json.dump({"deletable": deletable, "skipped": skipped}, fh, indent=1)
        print(f"snapshot written: {args.snapshot}")

    if not args.apply:
        print("\nDRY RUN - nothing deleted. Re-run with --apply to delete.")
        return 0

    removed, failed = delete_folders(deletable, args.host_root)
    print(f"\ndeleted: {len(removed)}")
    print(f"failed:  {len(failed)}")
    for name, err in failed[:20]:
        print(f"  FAIL {name[:60]} - {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
