#!/usr/bin/env python3
"""Turn checkrr's badfiles.csv into a verified, arr-attributed re-download list.

Why this exists
---------------
checkrr writes every file it could not validate to `badfiles.csv` with the
single reason string "unknown". That string is the *file type* verdict from
ffprobe ("is not a recognized file type"), not an arr-ownership verdict, and
it collapses two completely different situations into one row:

  1. Genuinely dead media. nzbdav serves these from Usenet, and when the
     articles backing the opening bytes have expired it fills the gap with
     zeros to preserve later file offsets (see the nzbdav_rclone log:
     "Filling the N-byte gap to preserve later file offsets"). ffprobe then
     reads 0x00 where the container magic should be and bails. Confirmed
     live 2026-08-12: 8/8 sampled .mkv rows failed with
     "0x00 at pos 0 (0x0) invalid as first byte of an EBML number".
     These need re-downloading.

  2. Formats ffprobe cannot demux at all - .iso / .img / .m2ts disc images.
     checkrr flags them every run and they are perfectly healthy. These are
     false positives and must not reach a re-download list.

Nothing in the CSV distinguishes them, so this script re-verifies every row
from scratch instead of trusting the reason column.

Verification method
-------------------
Container magic bytes, not a full ffprobe. The failure signature is a zeroed
file header, so reading the first 12 bytes is decisive and costs one small
FUSE read (~0.07s/file measured) instead of a full demux attempt over the
mount. A file whose header matches its extension is healthy; a zeroed header
is dead; anything else is reported as-is rather than guessed at.

`badfiles.csv` is cumulative across runs and repeats paths (2901 rows /
1251 unique paths on 2026-08-12), so rows are deduplicated first.

Attribution
-----------
Path prefix decides the owning arr, using the same mappings checkrr itself
uses in checkrr.yaml. Each arr is queried once for its whole library and
matched on the exact file path, so a title that Radarr/Sonarr no longer
tracks is reported as an orphan rather than silently dropped.

Safety
------
Report-only. This stack has a documented history of mass-deletion incidents
and checkrr runs with `process: false` for exactly that reason, so this
script never deletes, blocklists, unmonitors or triggers a search. With
--emit-commands it prints the commands that would do so, for review.

checkrr itself was removed from the stack on 2026-08-12. The dead files it
found did not go away with it, so this reads the archived final CSV at
data/checkrr-final/ rather than a running container.

Usage:
  python3 scripts/checkrr-badfiles-report.py [--csv PATH] [--out PATH]
                                             [--emit-commands] [--limit N]
                                             [--no-verify] [--jobs N]
"""
import argparse
import concurrent.futures
import csv
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# checkrr was removed 2026-08-12; its last scan output lives here.
ARCHIVED_CSV = "data/checkrr-final/badfiles-2026-08-12.csv"
ARCHIVED_CONFIG = "data/checkrr-final/checkrr.yaml"

# Container path prefix -> (host media dir, arr key in checkrr.yaml).
LIBRARIES = {
    "/data/movies/": ("media/movies", "radarr"),
    "/data/shows/": ("media/shows", "sonarr"),
    "/data/anime-movies/": ("media/anime-movies", "radarr_anime"),
    "/data/anime-shows/": ("media/anime-shows", "sonarr_anime"),
}

# Leading bytes a healthy container must start with. `offset` is where the
# signature sits; mp4/mov carry a size field in the first four bytes.
SIGNATURES = {
    ".mkv": (0, b"\x1a\x45\xdf\xa3"),
    ".mk3d": (0, b"\x1a\x45\xdf\xa3"),
    ".webm": (0, b"\x1a\x45\xdf\xa3"),
    ".mp4": (4, b"ftyp"),
    ".m4v": (4, b"ftyp"),
    ".mov": (4, b"ftyp"),
    ".avi": (0, b"RIFF"),
    ".ts": (0, b"\x47"),
    ".mpg": (0, b"\x00\x00\x01"),
    ".mpeg": (0, b"\x00\x00\x01"),
    ".wmv": (0, b"\x30\x26\xb2\x75"),
    ".flv": (0, b"FLV"),
}

# ffprobe cannot demux these, so checkrr flags them on every run regardless
# of health. Excluded from the re-download list by default.
UNPROBEABLE_EXTS = {".iso", ".img", ".m2ts", ".vob", ".bdmv", ".mpls"}

# Not media. checkrr picks these up when they sit beside a flagged file.
NON_MEDIA_EXTS = {".srt", ".sub", ".idx", ".ass", ".ssa", ".nfo", ".txt"}

STATUS_DEAD = "DEAD"
STATUS_HEALTHY = "HEALTHY"
STATUS_UNPROBEABLE = "UNPROBEABLE"
STATUS_NON_MEDIA = "NON_MEDIA"
STATUS_MISSING = "MISSING"
STATUS_UNREADABLE = "UNREADABLE"
STATUS_UNKNOWN_EXT = "UNKNOWN_EXT"


def parse_checkrr_yaml(path):
    """Pull the arr blocks out of checkrr.yaml without a yaml dependency.

    The file is flat and machine-written; a targeted parser keeps this script
    runnable on a bare interpreter, which matters because it is meant to be
    usable during an incident.
    """
    arrs = {}
    current = None
    in_arr = False
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            stripped = line.strip()
            if indent == 0:
                in_arr = stripped == "arr:"
                current = None
                continue
            if not in_arr:
                continue
            if indent == 2 and stripped.endswith(":"):
                current = stripped[:-1]
                arrs[current] = {"mappings": {}}
                continue
            if current is None or ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if indent >= 6:
                # A mappings entry: '"/data/movies/": "/data/movies/"'
                arrs[current]["mappings"][key.strip('"')] = value
            elif key != "mappings":
                arrs[current][key] = value
    return arrs


def load_badfiles(csv_path):
    """Return deduplicated paths from checkrr's cumulative CSV."""
    seen = {}
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh):
            if not row or not row[0].strip():
                continue
            path = row[0].strip()
            reason = row[-1].strip() if len(row) > 1 else ""
            seen.setdefault(path, reason)
    return seen


def container_to_host(path):
    """Map a checkrr container path to its path on the host."""
    for prefix, (host_dir, _) in LIBRARIES.items():
        if path.startswith(prefix):
            return os.path.join(REPO_ROOT, host_dir, path[len(prefix):])
    return None


def library_for(path):
    for prefix, (_, arr_key) in LIBRARIES.items():
        if path.startswith(prefix):
            return prefix, arr_key
    return None, None


def verify_file(path):
    """Classify one file by reading its container magic bytes.

    Returns (status, detail). Only the first 16 bytes are read, so a dead
    file costs roughly the same as a stat over the mount.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in NON_MEDIA_EXTS:
        return STATUS_NON_MEDIA, ext
    if ext in UNPROBEABLE_EXTS:
        return STATUS_UNPROBEABLE, ext

    host_path = container_to_host(path)
    if host_path is None:
        return STATUS_UNKNOWN_EXT, "path outside known libraries"
    if not os.path.exists(host_path):
        return STATUS_MISSING, "no such file (broken symlink or removed)"

    try:
        with open(host_path, "rb") as fh:
            head = fh.read(16)
    except OSError as exc:
        return STATUS_UNREADABLE, str(exc)

    if not head:
        return STATUS_DEAD, "empty file"
    if set(head[:8]) == {0}:
        return STATUS_DEAD, "zeroed header (missing articles on all providers)"

    sig = SIGNATURES.get(ext)
    if sig is None:
        return STATUS_UNKNOWN_EXT, head[:4].hex()
    offset, magic = sig
    if head[offset:offset + len(magic)] == magic:
        return STATUS_HEALTHY, "header ok"
    return STATUS_DEAD, f"bad header 0x{head[:4].hex()} (expected {magic!r})"


def resolve_host_port(arr):
    """Map an arr's container port to the port published on the host.

    checkrr reaches these over the docker network, where every Radarr is on
    7878 and every Sonarr on 8989. From the host they cannot all share those
    ports, so radarr-anime is published on 7879 and sonarr-anime on 8990.
    Using the container port from checkrr.yaml sends the anime API key to the
    general instance, which answers 401 - the bug this function exists to
    prevent. Asking docker keeps it correct if a published port ever moves.
    """
    container = arr.get("address")
    container_port = str(arr.get("port", ""))
    if not container:
        return container_port
    try:
        out = subprocess.run(["docker", "port", container, f"{container_port}/tcp"],
                             capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return container_port
    for line in out.stdout.splitlines():
        # "0.0.0.0:7879" / "[::]:7879" - take the first IPv4 binding.
        if ":" in line and not line.strip().startswith("["):
            return line.rsplit(":", 1)[1].strip()
    return container_port


def arr_get(arr, endpoint, timeout=180):
    """GET one endpoint off an arr instance, over its published host port."""
    port = arr.get("_host_port") or arr.get("port")
    url = f"http://localhost:{port}/api/v3/{endpoint}"
    req = urllib.request.Request(url, headers={"X-Api-Key": arr["apikey"]})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def build_radarr_index(arr):
    """path -> record for every movie file Radarr currently tracks."""
    index = {}
    for movie in arr_get(arr, "movie"):
        mf = movie.get("movieFile") or {}
        if not mf.get("path"):
            continue
        index[mf["path"]] = {
            "title": movie.get("title", ""),
            "year": movie.get("year", ""),
            "arr_id": movie.get("id"),
            "file_id": mf.get("id"),
            "quality": (mf.get("quality", {}).get("quality", {}) or {}).get("name", ""),
            "monitored": movie.get("monitored"),
            "detail": "",
        }
    return index


def build_sonarr_index(arr, wanted_paths):
    """path -> record, fetching episode files only for series we care about.

    Sonarr has no global episodefile endpoint, and pulling every series would
    mean thousands of round-trips. Series are matched to the flagged paths by
    folder prefix first so only the relevant ones are queried.
    """
    series_list = arr_get(arr, "series")
    by_path = {s["path"]: s for s in series_list if s.get("path")}

    needed = set()
    for path in wanted_paths:
        for series_path in by_path:
            if path.startswith(series_path.rstrip("/") + "/"):
                needed.add(series_path)
                break

    index = {}
    for series_path in sorted(needed):
        series = by_path[series_path]
        try:
            files = arr_get(arr, f"episodefile?seriesId={series['id']}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  warn: episodefile fetch failed for {series.get('title')}: {exc}",
                  file=sys.stderr)
            continue
        for ef in files:
            if not ef.get("path"):
                continue
            index[ef["path"]] = {
                "title": series.get("title", ""),
                "year": series.get("year", ""),
                "arr_id": series.get("id"),
                "file_id": ef.get("id"),
                "quality": (ef.get("quality", {}).get("quality", {}) or {}).get("name", ""),
                "monitored": series.get("monitored"),
                "detail": ef.get("relativePath", ""),
            }
    return index


def emit_commands(rows, arrs):
    """Print the remediation commands for review. Never runs them.

    Raw API calls rather than a wrapper: there is no stack fish function for
    "drop this file record and search again", and inventing one here would
    print something that does not run. Deleting the file record is what makes
    the arr consider the episode/movie missing again, so the search that
    follows has something to grab.
    """
    print("\n# --- REVIEW BEFORE RUNNING - nothing below has been executed ---")
    print("# Deletes the dead file record, then asks the arr to search again.")
    print("# Deleting a file record does NOT delete the file off the mount.")

    movies = [r for r in rows if r["arr"] in ("radarr", "radarr_anime") and r["file_id"]]
    shows = [r for r in rows if r["arr"] in ("sonarr", "sonarr_anime") and r["file_id"]]

    if movies:
        print("\n# ---- Movies ----")
        for r in sorted(movies, key=lambda x: str(x["title"])):
            arr = arrs.get(r["arr"], {})
            port, key = arr.get("port", "7878"), arr.get("apikey", "$RADARR_API_KEY")
            print(f'\n# {r["title"]} ({r["year"]}) [{r["quality"]}]')
            print(f'curl -sS -X DELETE -H "X-Api-Key: {key}" '
                  f'"http://localhost:{port}/api/v3/moviefile/{r["file_id"]}"')
            print(f'curl -sS -X POST -H "X-Api-Key: {key}" -H "Content-Type: application/json" '
                  f'-d \'{{"name":"MoviesSearch","movieIds":[{r["arr_id"]}]}}\' '
                  f'"http://localhost:{port}/api/v3/command"')

    if shows:
        print("\n# ---- Episodes ----")
        # One search per series, not per file: a series with 40 dead episodes
        # needs one SeriesSearch, and firing 40 would just queue duplicates.
        for r in sorted(shows, key=lambda x: (str(x["title"]), str(x["detail"]))):
            arr = arrs.get(r["arr"], {})
            port, key = arr.get("port", "8989"), arr.get("apikey", "$SONARR_API_KEY")
            print(f'# {r["title"]} - {r["detail"]} [{r["quality"]}]')
            print(f'curl -sS -X DELETE -H "X-Api-Key: {key}" '
                  f'"http://localhost:{port}/api/v3/episodefile/{r["file_id"]}"')

        print("\n# Then one search per affected series:")
        seen = set()
        for r in sorted(shows, key=lambda x: str(x["title"])):
            if (r["arr"], r["arr_id"]) in seen:
                continue
            seen.add((r["arr"], r["arr_id"]))
            arr = arrs.get(r["arr"], {})
            port, key = arr.get("port", "8989"), arr.get("apikey", "$SONARR_API_KEY")
            print(f'# {r["title"]}')
            print(f'curl -sS -X POST -H "X-Api-Key: {key}" -H "Content-Type: application/json" '
                  f'-d \'{{"name":"SeriesSearch","seriesId":{r["arr_id"]}}}\' '
                  f'"http://localhost:{port}/api/v3/command"')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=os.path.join(REPO_ROOT, ARCHIVED_CSV),
                    help=f"badfiles.csv (default: {ARCHIVED_CSV})")
    ap.add_argument("--config", default=os.path.join(REPO_ROOT, ARCHIVED_CONFIG))
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "checkrr-redownload.csv"))
    ap.add_argument("--limit", type=int, default=0, help="verify at most N files (0 = all)")
    ap.add_argument("--jobs", type=int, default=8, help="parallel header reads")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip magic-byte checks and trust the CSV")
    ap.add_argument("--emit-commands", action="store_true",
                    help="print remediation commands (does not run them)")
    args = ap.parse_args(argv)

    csv_path = args.csv
    if not os.path.exists(csv_path):
        print(f"error: {csv_path} not found. checkrr was removed on 2026-08-12; "
              f"pass --csv with an archived badfiles.csv.", file=sys.stderr)
        return 1
    entries = load_badfiles(csv_path)

    print(f"badfiles.csv: {len(entries)} unique paths", flush=True)

    paths = sorted(entries)
    if args.limit:
        paths = paths[:args.limit]

    # --- verify ---------------------------------------------------------
    results = {}
    if args.no_verify:
        for p in paths:
            results[p] = (STATUS_DEAD, "unverified (--no-verify)")
    else:
        print(f"verifying {len(paths)} files by container header ...", flush=True)
        # Reads go over the FUSE mount and a healthy file makes nzbdav open a
        # real Usenet session, so this can run for minutes. Progress is
        # flushed as it goes; without it a redirected run shows nothing at all
        # until the very end and looks hung.
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for path, outcome in zip(paths, pool.map(verify_file, paths)):
                results[path] = outcome
                done += 1
                if done % 100 == 0 or done == len(paths):
                    n_dead = sum(1 for s, _ in results.values() if s == STATUS_DEAD)
                    print(f"  {done}/{len(paths)} checked, {n_dead} dead so far",
                          flush=True)

    counts = defaultdict(int)
    for st, _ in results.values():
        counts[st] += 1
    print("\nverification:")
    for st in sorted(counts, key=lambda s: -counts[s]):
        print(f"  {st:12} {counts[st]}")

    dead = [p for p in paths if results[p][0] == STATUS_DEAD]
    print(f"\n{len(dead)} files need re-downloading", flush=True)

    # --- attribute ------------------------------------------------------
    arrs = parse_checkrr_yaml(args.config)
    by_arr = defaultdict(list)
    for p in dead:
        _, arr_key = library_for(p)
        by_arr[arr_key].append(p)

    rows = []
    for arr_key, arr_paths in sorted(by_arr.items()):
        arr = arrs.get(arr_key)
        if not arr:
            print(f"  warn: no {arr_key} block in checkrr.yaml", file=sys.stderr)
            continue
        arr["_host_port"] = resolve_host_port(arr)
        print(f"querying {arr_key} on localhost:{arr['_host_port']} "
              f"({len(arr_paths)} files) ...", flush=True)
        reachable = True
        try:
            if arr.get("service") == "radarr":
                index = build_radarr_index(arr)
            else:
                index = build_sonarr_index(arr, arr_paths)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            print(f"  warn: {arr_key} unreachable: {exc}", file=sys.stderr)
            index = {}
            reachable = False

        for p in arr_paths:
            rec = index.get(p)
            # An unreachable arr must never look like a confirmed orphan -
            # that misreads a connection fault as "no arr tracks this file".
            tracked = "yes" if rec else ("no" if reachable else "unknown")
            rows.append({
                "path": p,
                "arr": arr_key,
                "status": results[p][0],
                "reason": results[p][1],
                "tracked": tracked,
                "title": rec["title"] if rec else "",
                "year": rec["year"] if rec else "",
                "detail": rec["detail"] if rec else "",
                "quality": rec["quality"] if rec else "",
                "monitored": rec["monitored"] if rec else "",
                "arr_id": rec["arr_id"] if rec else "",
                "file_id": rec["file_id"] if rec else "",
            })

    # --- report ---------------------------------------------------------
    fields = ["path", "arr", "status", "reason", "tracked", "title", "year",
              "detail", "quality", "monitored", "arr_id", "file_id"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    tracked = [r for r in rows if r["tracked"] == "yes"]
    orphans = [r for r in rows if r["tracked"] == "no"]
    unknown = [r for r in rows if r["tracked"] == "unknown"]
    print(f"\nwrote {args.out}")
    print(f"  tracked by an arr (re-downloadable): {len(tracked)}")
    print(f"  orphaned (no arr record):            {len(orphans)}")
    if unknown:
        print(f"  UNDETERMINED (arr unreachable):      {len(unknown)}")

    per_arr = defaultdict(lambda: [0, 0, 0])
    slot = {"yes": 0, "no": 1, "unknown": 2}
    for r in rows:
        per_arr[r["arr"]][slot[r["tracked"]]] += 1
    print("\n  by instance:      tracked  orphan  undet")
    for arr_key in sorted(per_arr):
        t, o, u = per_arr[arr_key]
        print(f"    {arr_key:14} {t:7} {o:7} {u:6}")

    titles = defaultdict(int)
    for r in tracked:
        if r["title"]:
            titles[r["title"]] += 1
    if titles:
        print("\n  worst-hit titles:")
        for title, n in sorted(titles.items(), key=lambda kv: -kv[1])[:15]:
            print(f"    {n:4}  {title}")

    if args.emit_commands:
        emit_commands(tracked, arrs)

    return 0


if __name__ == "__main__":
    sys.exit(main())
