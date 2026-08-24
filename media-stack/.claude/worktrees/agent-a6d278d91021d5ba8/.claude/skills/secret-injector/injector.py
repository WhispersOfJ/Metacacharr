#!/usr/bin/env python3
"""Audit, validate, and safely inject secrets into the media-stack's .env file.

Never accepts secret values as CLI arguments and never prints values.

Usage:
    injector.py audit [--env-file .env] [--compose-file docker-compose.yml]
    injector.py validate [--env-file .env]
    injector.py set KEY [--force] [--env-file .env]   (value read from stdin)
    injector.py leak-scan [--env-file .env] [--root .]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VAR_REF_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-[^}]*)?\}")

# (regex, human description) — used for lightweight format sanity checks.
KEY_PATTERNS: dict[str, tuple[str, str]] = {
    "RADARR_API_KEY": (r"^[a-f0-9]{32}$", "32-char lowercase hex"),
    "SONARR_API_KEY": (r"^[a-f0-9]{32}$", "32-char lowercase hex"),
    "PROWLARR_API_KEY": (r"^[a-f0-9]{32}$", "32-char lowercase hex"),
    "RADARR_ANIME_API_KEY": (r"^[a-f0-9]{32}$", "32-char lowercase hex"),
    "SONARR_ANIME_API_KEY": (r"^[a-f0-9]{32}$", "32-char lowercase hex"),
    # NzbDAV shares one key across its frontend proxy, SAB API, and admin
    # API (unlike BearMount's separate BEARMOUNT_API_KEY) - see STACK.md's
    # History for the 2026-07-28 cutover.
    "FRONTEND_BACKEND_API_KEY": (r"^[a-f0-9]{32}$", "32-char lowercase hex"),
}


def parse_env_file(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return {}
    result = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def referenced_keys(compose_file: Path) -> set[str]:
    if not compose_file.exists():
        return set()
    text = compose_file.read_text()
    return set(VAR_REF_RE.findall(text))


def cmd_audit(env_file: Path, compose_file: Path) -> int:
    present = parse_env_file(env_file)
    required = referenced_keys(compose_file)
    missing = sorted(required - present.keys())
    if not missing:
        print(f"all {len(required)} referenced keys are present in {env_file}")
        return 0
    print(f"{len(missing)} key(s) referenced in {compose_file} but missing from {env_file}:")
    for key in missing:
        print(f"  - {key}")
    return 1


def cmd_validate(env_file: Path) -> int:
    present = parse_env_file(env_file)
    all_ok = True
    for key, value in present.items():
        if key not in KEY_PATTERNS:
            continue
        pattern, desc = KEY_PATTERNS[key]
        ok = bool(re.match(pattern, value))
        print(f"{'OK  ' if ok else 'FAIL'}  {key} (expected {desc})")
        all_ok = all_ok and ok
    return 0 if all_ok else 1


def cmd_set(env_file: Path, key: str, force: bool) -> int:
    if not sys.stdin.isatty():
        value = sys.stdin.readline().rstrip("\n")
    else:
        import getpass
        value = getpass.getpass(f"value for {key} (hidden): ")

    if not value:
        print("error: empty value refused", file=sys.stderr)
        return 1

    present = parse_env_file(env_file)
    if key in present and not force:
        print(f"error: {key} already set in {env_file}; pass --force to overwrite", file=sys.stderr)
        return 1

    lines = env_file.read_text().splitlines() if env_file.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    env_file.write_text("\n".join(lines) + "\n")
    print(f"{key} written to {env_file} (value not shown)")
    return 0


def cmd_leak_scan(env_file: Path, root: Path) -> int:
    present = parse_env_file(env_file)
    values = {v: k for k, v in present.items() if len(v) >= 8}  # skip trivially short values
    if not values:
        print("no secret values to scan for")
        return 0

    skip_dirs = {".git", "node_modules", ".venv", "__pycache__"}
    hits = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == env_file.resolve():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(errors="ignore")
        except (UnicodeDecodeError, PermissionError):
            continue
        for value, key in values.items():
            if value in text:
                line_no = text[: text.index(value)].count("\n") + 1
                print(f"LEAK  {key} value found in {path} (line {line_no}, value redacted)")
                hits += 1

    if hits == 0:
        print("no leaked secret values found")
    return 1 if hits else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--compose-file", type=Path, default=Path("docker-compose.yml"))
    parser.add_argument("--root", type=Path, default=Path("."))
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("audit")
    sub.add_parser("validate")

    p_set = sub.add_parser("set")
    p_set.add_argument("key")
    p_set.add_argument("--force", action="store_true")

    sub.add_parser("leak-scan")

    args = parser.parse_args()

    if args.action == "audit":
        return cmd_audit(args.env_file, args.compose_file)
    if args.action == "validate":
        return cmd_validate(args.env_file)
    if args.action == "set":
        return cmd_set(args.env_file, args.key, args.force)
    if args.action == "leak-scan":
        return cmd_leak_scan(args.env_file, args.root)
    return 1


if __name__ == "__main__":
    sys.exit(main())
