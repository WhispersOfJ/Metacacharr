#!/usr/bin/env python3
"""Rename fish commands across every file that names one as a string.

Phase 8b of docs/superpowers/specs/2026-08-13-cli-naming-cleanup-design.md.

Hard cutover: no aliases, no transition period. Every reference moves in one
commit, and the script proves it by grepping for each old name afterwards.

Usage:
    fish-rename.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The 12 renames from the spec. Ten are verb order; two give a command the
# domain its name was missing.
RENAMES = {
    "stack-arr-blocklist-clear": "stack-arr-clear-blocklist",
    "stack-arr-search-toggle": "stack-arr-toggle-search",
    "stack-plex-rss-import": "stack-plex-import-rss",
    "stack-plex-watchlist-import": "stack-plex-import-watchlist",
    "stack-radarr-list-import": "stack-radarr-import-list",
    "stack-sonarr-custom-list-import": "stack-sonarr-import-custom-list",
    "stack-sonarr-monitor-episodes-fix": "stack-sonarr-fix-episode-monitoring",
    "stack-tmdb-company-import": "stack-tmdb-import-company",
    "stack-tmdb-keyword-import": "stack-tmdb-import-keyword",
    "stack-trakt-list-import": "stack-trakt-import-list",
    "stack-recently-added": "stack-arr-recently-added",
    "stack-disk-usage": "stack-disk-config-sizes",
}


def rename_text(text: str, renames: dict[str, str]) -> str:
    """Replace whole command names only.

    One regex pass over the alternation, longest name first, so
    `stack-arr-import` can never eat `stack-arr-import-all`, and so a rename
    map where one name's target is another's source does not cascade. The
    boundary is "not followed by another name character", which keeps
    `stack-plex-rss-importer` and `xstack-...` intact while still matching
    inside quotes, paths and `.fish` suffixes.
    """
    if not renames:
        return text
    ordered = sorted(renames, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in ordered) + r")(?![\w-])")
    return pattern.sub(lambda m: renames[m.group(1)], text)


# Files that describe the rename rather than use the commands. Rewriting these
# would corrupt the record: the spec's table literally reads
# "stack-arr-blocklist-clear -> stack-arr-clear-blocklist", and a blind pass
# would turn both sides into the new name. PLANS.md 8.3 is the same shape - a
# pre-rename audit of the inconsistencies, already marked superseded by
# Phase 8's status line. test_fish_naming.py names the old forms in the
# docstring that explains why the linter caught 7 of them and not 12.
#
# Determined by grepping the repo for all 12 old names before the first run,
# not guessed - every other hit was a live reference.
RECORD_PATHS = {
    "PLANS.md",
    "tests/test_fish_naming.py",
    # This script's own tests use real old names as fixtures. Rewriting them
    # collapses `{"old": "new"}` into `{"new": "new"}` - an identity mapping
    # that still passes and asserts nothing.
    "tests/scripts/test_fish_rename.py",
}
RECORD_PREFIXES = ("docs/superpowers/",)


def _is_record(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root).as_posix()
    return rel in RECORD_PATHS or rel.startswith(RECORD_PREFIXES)


def targets(repo_root: Path) -> list[Path]:
    """Every file that can name a command as a string, minus the record files.

    Wider than "docs and fish functions": control-panel routers name .fish
    files in comments explaining which auth dependency a command needs, and
    router tests name the command that exercises them. Both go stale silently.
    """
    found: list[Path] = []
    found.extend(sorted((repo_root / "fish-functions").glob("*.fish")))
    found.extend(sorted((repo_root / "fish-functions").glob("*.md")))
    commands = repo_root / "control-panel/static/commands.json"
    if commands.is_file():
        found.append(commands)
    found.extend(sorted((repo_root / ".claude/skills").rglob("SKILL.md")))
    found.extend(sorted((repo_root / "control-panel").rglob("*.py")))
    found.extend(sorted((repo_root / "tests").rglob("*.py")))
    for name in ("README.md", "STACK.md", "AGENTS.md", "PLANS.md", "CLAUDE.md"):
        path = repo_root / name
        if path.is_file():
            found.append(path)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in found:
        if path in seen or _is_record(path, repo_root):
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def _rename_files(dry_run: bool) -> list[str]:
    """Rename the .fish files themselves - fish autoloads by filename, so a
    file left under the old name keeps the old command alive."""
    lines = []
    for old, new in RENAMES.items():
        source = REPO_ROOT / "fish-functions" / f"{old}.fish"
        if not source.is_file():
            continue
        lines.append(f"git mv {old}.fish {new}.fish")
        if not dry_run:
            subprocess.run(["git", "mv", str(source), str(source.with_name(f"{new}.fish"))],
                           cwd=REPO_ROOT, check=True)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for path in targets(REPO_ROOT):
        original = path.read_text()
        updated = rename_text(original, RENAMES)
        if updated != original:
            print(f"edit   {path.relative_to(REPO_ROOT)}")
            if not args.dry_run:
                path.write_text(updated)

    for line in _rename_files(args.dry_run):
        print(line)

    if args.dry_run:
        return 0

    subprocess.run([str(REPO_ROOT / ".venv-test/bin/python"),
                    str(REPO_ROOT / "scripts/fish-functions-install.py")], check=True)

    leftovers = []
    for old in RENAMES:
        result = subprocess.run(["git", "grep", "-n", "--", old], cwd=REPO_ROOT,
                                capture_output=True, text=True)
        # A hit in a record file is expected, not a miss - those files describe
        # the rename. Filter them out so the check stays a real assertion.
        hits = [line for line in result.stdout.splitlines()
                if line and not _is_record(REPO_ROOT / line.split(":", 1)[0], REPO_ROOT)]
        if hits:
            leftovers.append(f"{old}:\n" + "\n".join(hits))
    if leftovers:
        print("\nOLD NAMES STILL PRESENT:\n" + "\n".join(leftovers))
        return 1
    print("\nNo old names remain in tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
