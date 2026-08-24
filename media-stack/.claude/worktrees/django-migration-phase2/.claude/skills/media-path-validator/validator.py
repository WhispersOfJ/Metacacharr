#!/usr/bin/env python3
"""Validate media-stack download/library paths: existence, writability, hardlink-ability.

Usage:
    validator.py check <download_path> <library_path>
    validator.py check-all --config paths.json
    validator.py writable <path>
    validator.py exists <path> [path...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


def check_exists(path: Path) -> bool:
    return path.exists()


def check_writable(path: Path) -> bool:
    return os.access(path, os.W_OK)


def check_hardlink(download_path: Path, library_path: Path) -> tuple[bool, str]:
    """Probe whether os.link() would succeed between the two paths (same filesystem)."""
    if not download_path.exists() or not library_path.exists():
        return False, "one or both paths do not exist"

    try:
        dev_download = download_path.stat().st_dev
        dev_library = library_path.stat().st_dev
    except OSError as e:
        return False, f"stat failed: {e}"

    if dev_download != dev_library:
        return False, f"different filesystems (st_dev {dev_download} vs {dev_library})"

    # Live probe: create a temp file in the download path, try to hardlink it into
    # the library path, then clean up immediately.
    try:
        with tempfile.NamedTemporaryFile(dir=download_path, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        link_path = library_path / f".hardlink-probe-{tmp_path.name}"
        try:
            os.link(tmp_path, link_path)
            link_path.unlink()
            return True, "same filesystem, hardlink probe succeeded"
        finally:
            tmp_path.unlink(missing_ok=True)
    except OSError as e:
        return False, f"hardlink probe failed: {e}"


def cmd_exists(paths: list[str]) -> int:
    ok = True
    for p in paths:
        path = Path(p)
        exists = check_exists(path)
        print(f"{'OK  ' if exists else 'MISS'}  {p}")
        ok = ok and exists
    return 0 if ok else 1


def cmd_writable(path_str: str) -> int:
    path = Path(path_str)
    if not check_exists(path):
        print(f"MISS  {path_str} does not exist")
        return 1
    writable = check_writable(path)
    print(f"{'OK  ' if writable else 'FAIL'}  {path_str} writable={writable}")
    return 0 if writable else 1


def _report_pair(label: str, download: str, library: str) -> bool:
    d, lib = Path(download), Path(library)
    exists_d, exists_l = check_exists(d), check_exists(lib)
    if not (exists_d and exists_l):
        print(f"[{label}] {download} exists={exists_d}  {library} exists={exists_l}  -> SKIPPED (missing path)")
        return False
    writable_l = check_writable(lib)
    linkable, reason = check_hardlink(d, lib)
    status = "OK" if linkable else "PROBLEM"
    print(f"[{label}] {download} -> {library}: {status} ({reason}); library writable={writable_l}")
    return linkable


def cmd_check(download: str, library: str) -> int:
    ok = _report_pair("check", download, library)
    return 0 if ok else 1


def cmd_check_all(config_path: Path) -> int:
    config = json.loads(config_path.read_text())
    pairs = config.get("pairs", [])
    if not pairs:
        print("no pairs defined in config")
        return 1
    all_ok = True
    for pair in pairs:
        label = pair.get("label", "unlabeled")
        ok = _report_pair(label, pair["download"], pair["library"])
        all_ok = all_ok and ok
    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    p_check = sub.add_parser("check")
    p_check.add_argument("download_path")
    p_check.add_argument("library_path")

    p_check_all = sub.add_parser("check-all")
    p_check_all.add_argument("--config", type=Path, required=True)

    p_writable = sub.add_parser("writable")
    p_writable.add_argument("path")

    p_exists = sub.add_parser("exists")
    p_exists.add_argument("paths", nargs="+")

    args = parser.parse_args()

    if args.action == "check":
        return cmd_check(args.download_path, args.library_path)
    if args.action == "check-all":
        return cmd_check_all(args.config)
    if args.action == "writable":
        return cmd_writable(args.path)
    if args.action == "exists":
        return cmd_exists(args.paths)
    return 1


if __name__ == "__main__":
    sys.exit(main())
