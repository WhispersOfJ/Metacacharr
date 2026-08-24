# CLI Naming Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repo the single enforced source of truth for this stack's 190 `stack-*` fish functions, then rename the 12 that violate the naming schema, behind a linter that keeps it that way.

**Architecture:** Two ordered phases. 8a (Tasks 1-5) replaces the hand-copied `~/.config/fish/functions/stack-*.fish` files with symlinks into the repo's `fish-functions/`, deletes 5 dead restic-era functions, writes 4 functions that `commands.json` already advertises, and locks the invariant with a gate test. 8b (Tasks 6-8) adds a schema linter whose failure output is the audit, then a rename script that edits every reference in one pass. 8b must not start until Task 5 is committed and green.

**Execution note (2026-08-13):** this runs on `main` with the human partner's explicit consent, not in a worktree — Tasks 2, 3 and 7 create symlinks in `~/.config/fish/functions` that must point at `/home/bear/Claude/media-stack/fish-functions`, and a worktree would leave 194 dangling links behind when it was removed. The original Tasks 7-9 were merged into Tasks 7-8 so that no task ever commits a failing test.

**Tech Stack:** Python 3.13 (`.venv-test/bin/python`), pytest, fish 4.x, no new dependencies.

## Global Constraints

- Source spec: `docs/superpowers/specs/2026-08-13-cli-naming-cleanup-design.md`. Where this plan and the spec disagree, the spec wins.
- Run tests with `.venv-test/bin/python -m pytest` from the repo root. Never `python3 -m pytest` — the venv holds fastapi/httpx.
- Full-suite baseline before this work: **824 passing**. Any task that ends with fewer than its own additions on top of that number is a regression, not a milestone.
- Gate-lane rules (CLAUDE.md): the new tests must be deterministic, local, free, and under 2 seconds. No network, no Docker, no live control-panel calls.
- Control-panel REST paths (`/api/*`) are frozen. No task in this plan edits a route path.
- Host-domain commands (35 of them) and the source-first family (21) are allowlisted, never renamed.
- `commands.json` is edited key-by-key, never by `json.dump` round-trip. A round-trip re-escapes em dashes (`—` → `—`) across unrelated entries; this happened on 2026-08-13 and had to be reverted.
- Never use `status` as a variable name in fish or shell code in this repo.
- Commit after every task. No `--no-verify`.

---

### Task 1: Symlink installer and its gate test

Replaces hand-copying with symlinks, so repo and host cannot drift. The installer also prunes `stack-*` files on the host that no longer exist in the repo, which is what removes the 5 restic orphans in Task 2.

**Files:**
- Create: `scripts/fish-functions-install.py`
- Create: `tests/scripts/test_fish_functions_install.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `plan(repo_dir: Path, installed_dir: Path) -> dict` returning `{"link": [Path], "relink": [Path], "prune": [Path], "keep": [Path]}` where every value is a path in `installed_dir`; and `apply(actions: dict, repo_dir: Path = DEFAULT_REPO_DIR, dry_run: bool = False) -> list[str]` returning human-readable action lines. Task 2 calls the CLI, not these functions directly.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_fish_functions_install.py`:

```python
"""Phase 8a: the symlink installer that makes fish-functions/ the single
source of truth.

Two sources of truth existed before this: the repo's fish-functions/ and the
host's ~/.config/fish/functions/, hand-copied between. They drifted 9 names
apart. Symlinks make drift structurally impossible rather than discouraged,
which is the same pattern this repo's systemd units already use.

The prune path is the sharp edge: it deletes files from the user's live shell
environment, so it must only ever touch stack-*.fish, never a real file the
user wrote by hand outside this repo, and never anything without the prefix.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/fish-functions-install.py"


@pytest.fixture(scope="module")
def installer():
    spec = importlib.util.spec_from_file_location("_script_fish_functions_install", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_script_fish_functions_install"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dirs(tmp_path):
    repo = tmp_path / "fish-functions"
    installed = tmp_path / "functions"
    repo.mkdir()
    installed.mkdir()
    return repo, installed


def _write(directory: Path, name: str, body: str = "function x\nend\n") -> Path:
    path = directory / f"{name}.fish"
    path.write_text(body)
    return path


def test_missing_function_is_linked(installer, dirs):
    repo, installed = dirs
    _write(repo, "stack-plex-scan")
    actions = installer.plan(repo, installed)
    assert actions["link"] == [installed / "stack-plex-scan.fish"]
    installer.apply(actions, repo_dir=repo)
    link = installed / "stack-plex-scan.fish"
    assert link.is_symlink()
    assert link.resolve() == (repo / "stack-plex-scan.fish").resolve()


def test_plain_copy_is_replaced_by_a_link(installer, dirs):
    """The starting state on the real host: 191 plain copies."""
    repo, installed = dirs
    _write(repo, "stack-plex-scan", "function new\nend\n")
    _write(installed, "stack-plex-scan", "function stale copy\nend\n")
    actions = installer.plan(repo, installed)
    assert actions["relink"] == [installed / "stack-plex-scan.fish"]
    installer.apply(actions, repo_dir=repo)
    assert (installed / "stack-plex-scan.fish").is_symlink()
    assert (installed / "stack-plex-scan.fish").read_text() == "function new\nend\n"


def test_host_only_stack_function_is_pruned(installer, dirs):
    """The 5 restic orphans: installed, not in the repo, dead."""
    repo, installed = dirs
    _write(installed, "stack-backup-verify")
    actions = installer.plan(repo, installed)
    assert actions["prune"] == [installed / "stack-backup-verify.fish"]
    installer.apply(actions, repo_dir=repo)
    assert not (installed / "stack-backup-verify.fish").exists()


def test_non_stack_functions_are_never_touched(installer, dirs):
    """The user's own fish functions live in the same directory. Pruning one
    would delete work that has no other copy anywhere."""
    repo, installed = dirs
    _write(installed, "my-own-helper")
    _write(installed, "__stack_api")
    actions = installer.plan(repo, installed)
    assert actions["prune"] == []
    installer.apply(actions, repo_dir=repo)
    assert (installed / "my-own-helper.fish").exists()
    assert (installed / "__stack_api.fish").exists()


def test_correct_link_is_left_alone(installer, dirs):
    """Idempotence: a second run does nothing, so it is safe to re-run."""
    repo, installed = dirs
    source = _write(repo, "stack-plex-scan")
    (installed / "stack-plex-scan.fish").symlink_to(source)
    actions = installer.plan(repo, installed)
    assert actions == {"link": [], "relink": [], "prune": [], "keep": [installed / "stack-plex-scan.fish"]}


def test_dangling_link_is_repaired(installer, dirs):
    """A link left behind by a renamed function points at nothing. It is a
    prune, not a relink - the repo no longer has that name."""
    repo, installed = dirs
    (installed / "stack-gone.fish").symlink_to(repo / "stack-gone.fish")
    actions = installer.plan(repo, installed)
    assert actions["prune"] == [installed / "stack-gone.fish"]
    installer.apply(actions, repo_dir=repo)
    assert not (installed / "stack-gone.fish").is_symlink()


def test_dry_run_changes_nothing(installer, dirs):
    repo, installed = dirs
    _write(repo, "stack-plex-scan")
    _write(installed, "stack-backup-verify")
    lines = installer.apply(installer.plan(repo, installed), repo_dir=repo, dry_run=True)
    assert not (installed / "stack-plex-scan.fish").exists()
    assert (installed / "stack-backup-verify.fish").exists()
    assert any("stack-plex-scan" in line for line in lines)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-test/bin/python -m pytest tests/scripts/test_fish_functions_install.py -q`
Expected: collection error — `scripts/fish-functions-install.py` does not exist.

- [ ] **Step 3: Write the installer**

Create `scripts/fish-functions-install.py`:

```python
#!/usr/bin/env python3
"""Install this repo's fish functions into the user's fish function directory
as symlinks.

Phase 8a of docs/superpowers/specs/2026-08-13-cli-naming-cleanup-design.md.

Before this, fish-functions/ was hand-copied to ~/.config/fish/functions/ and
the two drifted 9 names apart - 4 functions existed only in the repo, 5 only
on the host. Symlinks remove the possibility rather than the habit.

Only files matching stack-*.fish are managed. Everything else in the target
directory belongs to the user, including __stack_api.fish, and is never
touched - it is the one directory where deleting the wrong file destroys work
with no other copy.

Usage:
    fish-functions-install.py [--dry-run] [--repo-dir DIR] [--installed-dir DIR]
"""
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_REPO_DIR = Path(__file__).resolve().parent.parent / "fish-functions"
DEFAULT_INSTALLED_DIR = Path.home() / ".config/fish/functions"
MANAGED_GLOB = "stack-*.fish"


def plan(repo_dir: Path, installed_dir: Path) -> dict:
    """Decide what to do without doing it.

    Returns four disjoint lists of paths in `installed_dir`: link (nothing
    there yet), relink (something there that is not the right link), prune
    (managed name with no repo source), keep (already correct).
    """
    actions: dict[str, list[Path]] = {"link": [], "relink": [], "prune": [], "keep": []}
    sources = {path.name: path for path in sorted(repo_dir.glob(MANAGED_GLOB))}

    for name, source in sources.items():
        target = installed_dir / name
        if not target.is_symlink() and not target.exists():
            actions["link"].append(target)
        elif target.is_symlink() and target.resolve() == source.resolve():
            actions["keep"].append(target)
        else:
            # A plain copy, or a link pointing somewhere else.
            actions["relink"].append(target)

    for target in sorted(installed_dir.glob(MANAGED_GLOB)):
        if target.name not in sources:
            actions["prune"].append(target)
    # A dangling symlink is not matched by glob() on some Python versions;
    # iterate the directory directly so a link to a deleted source is caught.
    for target in sorted(installed_dir.iterdir()):
        if (target.is_symlink() and not target.exists()
                and target.name.startswith("stack-") and target.name.endswith(".fish")
                and target.name not in sources and target not in actions["prune"]):
            actions["prune"].append(target)

    return actions


def apply(actions: dict, repo_dir: Path = DEFAULT_REPO_DIR, dry_run: bool = False) -> list[str]:
    """Perform the planned actions. Returns one description line per action.

    `repo_dir` is explicit rather than read from the module default so the
    tests can drive this against a tmp_path repo - and so a caller can never
    plan against one directory and apply against another.
    """
    lines: list[str] = []

    for target in actions["link"] + actions["relink"]:
        source = repo_dir / target.name
        verb = "link" if target in actions["link"] else "relink"
        lines.append(f"{verb}  {target} -> {source}")
        if dry_run:
            continue
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(source)

    for target in actions["prune"]:
        lines.append(f"prune  {target}")
        if not dry_run:
            target.unlink()

    lines.append(f"keep   {len(actions['keep'])} already-correct link(s)")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--installed-dir", type=Path, default=DEFAULT_INSTALLED_DIR)
    args = parser.parse_args()

    args.installed_dir.mkdir(parents=True, exist_ok=True)
    for line in apply(plan(args.repo_dir, args.installed_dir),
                      repo_dir=args.repo_dir, dry_run=args.dry_run):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv-test/bin/python -m pytest tests/scripts/test_fish_functions_install.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/fish-functions-install.py tests/scripts/test_fish_functions_install.py
git commit -m "feat: symlink installer for fish functions (Phase 8a)"
```

---

### Task 2: Run the installer for real, and add the drift gate test

Executes the cutover on the live host and locks it. This is the task that deletes the 5 restic orphans and installs the 4 repo-only `stack-mdblist-radarr-*` functions — both fall out of the installer, neither needs a bespoke step.

**Files:**
- Create: `tests/test_fish_functions_installed.py`
- Delete: `control-panel/services/backups/` (empty directory left by the 2026-08-12 restic removal)

**Interfaces:**
- Consumes: `scripts/fish-functions-install.py` from Task 1.
- Produces: nothing importable.

- [ ] **Step 1: Dry-run the installer and read the output**

Run: `.venv-test/bin/python scripts/fish-functions-install.py --dry-run`
Expected: 190 relink lines, 5 prune lines (`stack-backup-integrity-check`, `stack-backup-restore-test`, `stack-backup-status`, `stack-backup-verify`, `stack-newapps-backup-check`), 4 link lines (`stack-mdblist-radarr-{history,track,tracked,untrack}`), 0 keep.

If the prune list contains anything other than those 5 names, STOP and report — pruning is the one irreversible action here.

- [ ] **Step 2: Write the failing gate test**

Create `tests/test_fish_functions_installed.py`:

```python
"""Phase 8a: the invariant that keeps fish-functions/ the only source of truth.

This test is why the drift cannot come back. It fails the commit if any
stack-* function on this host is a plain copy instead of a symlink into the
repo, or if either side has a name the other does not.

It is host-coupled by design: it asserts something about the live shell
environment, not about repo contents. On a machine with no ~/.config/fish it
skips rather than fails, so CI and a fresh clone stay green.
"""
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent / "fish-functions"
INSTALLED_DIR = Path.home() / ".config/fish/functions"

pytestmark = pytest.mark.skipif(
    not INSTALLED_DIR.is_dir(),
    reason="no fish function directory on this host",
)


def _names(directory: Path) -> set[str]:
    return {path.name for path in directory.glob("stack-*.fish")}


def test_every_installed_stack_function_is_a_symlink_into_the_repo():
    offenders = []
    for path in sorted(INSTALLED_DIR.glob("stack-*.fish")):
        if not path.is_symlink():
            offenders.append(f"{path.name}: plain copy, not a link")
        elif path.resolve() != (REPO_DIR / path.name).resolve():
            offenders.append(f"{path.name}: links to {path.resolve()}")
    assert not offenders, (
        "Run scripts/fish-functions-install.py. Offenders:\n  " + "\n  ".join(offenders))


def test_repo_and_installed_name_sets_are_identical():
    repo, installed = _names(REPO_DIR), _names(INSTALLED_DIR)
    assert repo == installed, (
        f"repo-only: {sorted(repo - installed)}\n"
        f"installed-only: {sorted(installed - repo)}\n"
        "Run scripts/fish-functions-install.py.")


def test_no_dangling_links():
    dangling = [p.name for p in INSTALLED_DIR.iterdir()
                if p.name.startswith("stack-") and p.is_symlink() and not p.exists()]
    assert not dangling, f"dangling links: {dangling}"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv-test/bin/python -m pytest tests/test_fish_functions_installed.py -q`
Expected: FAIL — 191 plain copies, and both name-set differences reported.

- [ ] **Step 4: Run the installer for real**

Run: `.venv-test/bin/python scripts/fish-functions-install.py`

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv-test/bin/python -m pytest tests/test_fish_functions_installed.py -q`
Expected: 3 passed.

- [ ] **Step 6: Verify the live shell still works**

Run: `fish -c 'stack-plex-libraries' | head -3` and `fish -c 'stack-mdblist-radarr-tracked' | head -3`
Expected: both answer. The second proves a newly-installed function works, not just a relinked one.

- [ ] **Step 7: Remove the empty backups service directory**

```bash
rm -rf control-panel/services/backups
```

Confirm it held only `__pycache__` before deleting. `control-panel/main.py` imports `services.<name>.router` for each directory, so an empty one is a latent import error.

- [ ] **Step 8: Commit**

```bash
git add tests/test_fish_functions_installed.py
git add -A control-panel/services
git commit -m "feat: cut fish functions over to symlinks, drop restic orphans (Phase 8a)"
```

---

### Task 3: Write the 4 functions commands.json already advertises

`commands.json` describes four CLI commands whose fish functions were never written. Their routes are live. This task writes them from the entries' own specs.

**Files:**
- Create: `fish-functions/stack-loop-candidates.fish`
- Create: `fish-functions/stack-loop-unmonitor.fish`
- Create: `fish-functions/stack-loop-exclude.fish`
- Create: `fish-functions/stack-nzbdav-dedup-check.fish`

**Interfaces:**
- Consumes: `__stack_api METHOD PATH [JSON_BODY]` (existing).
- Produces: four fish functions; Task 4's linter will check their names.

- [ ] **Step 1: Write the four functions**

`fish-functions/stack-loop-candidates.fish`:

```fish
# Usage: stack-loop-candidates <radarr|sonarr>
# Titles or episodes looping in the queue-autofix history - 2+ downloadFailed
# events in the last N hours - with a suggested remediation for each.
# The companions are stack-loop-unmonitor (stops the loop) and
# stack-loop-exclude (stops import lists re-monitoring it afterwards).
function stack-loop-candidates --description 'Looping titles in the queue-autofix history, with remediation'
    if test (count $argv) -lt 1; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-loop-candidates <radarr|sonarr>" >&2
        return 1
    end
    __stack_api GET "/api/arr/$argv[1]/loop-candidates"
end
```

`fish-functions/stack-loop-unmonitor.fish`:

```fish
# Usage: stack-loop-unmonitor <radarr|sonarr> <id> [-y|--yes]
# Unmonitors a movie (Radarr) or episode (Sonarr) by id - the fix for a
# confirmed loop candidate. Confirms first unless -y is given.
#
# For Radarr this is often not enough on its own: an import list sync can
# re-monitor the movie afterwards. stack-loop-exclude is the durable fix.
function stack-loop-unmonitor --description 'Unmonitor a looping movie or episode by id'
    if test (count $argv) -lt 2; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-loop-unmonitor <radarr|sonarr> <id> [-y|--yes]" >&2
        return 1
    end
    set -l app $argv[1]
    set -l item_id $argv[2]
    if not contains -- -y $argv; and not contains -- --yes $argv
        read -l -P "Unmonitor $app item $item_id? [y/N] " confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST "/api/arr/$app/unmonitor" "{\"ids\": [$item_id]}"
end
```

`fish-functions/stack-loop-exclude.fish`:

```fish
# Usage: stack-loop-exclude <movie-id> [-y|--yes]
# Adds a Radarr movie to Exclusions - the durable fix for a movie that gets
# re-monitored by import-list syncs after stack-loop-unmonitor.
# Radarr only; Sonarr has no equivalent exclusion list for episodes.
function stack-loop-exclude --description 'Add a Radarr movie to Exclusions'
    if test (count $argv) -lt 1
        echo "Usage: stack-loop-exclude <movie-id> [-y|--yes]" >&2
        return 1
    end
    set -l movie_id $argv[1]
    if not contains -- -y $argv; and not contains -- --yes $argv
        read -l -P "Exclude Radarr movie $movie_id from all import lists? [y/N] " confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST "/api/arr/radarr/exclude" "{\"movieId\": $movie_id}"
end
```

`fish-functions/stack-nzbdav-dedup-check.fish`:

```fish
# Usage: stack-nzbdav-dedup-check
# Verifies NzbDAV's api.duplicate-nzb-behavior is still mark-failed. Guards
# against the return of the (2)/(3)-suffix importBlocked bug, where a
# duplicate grab lands as "Title (2)" and the Arr app cannot import it.
function stack-nzbdav-dedup-check --description 'Verify NzbDAV duplicate-nzb-behavior is still mark-failed'
    __stack_api GET /api/nzbdav/dedup-config-check
end
```

- [ ] **Step 2: Install and smoke-test them**

Run:
```bash
.venv-test/bin/python scripts/fish-functions-install.py
fish -c 'stack-nzbdav-dedup-check'
fish -c 'stack-loop-candidates radarr' | head -3
fish -c 'stack-loop-candidates'          # expect the usage error, exit 1
```
Expected: the first two print a real API answer; the third prints usage to stderr and returns 1.

- [ ] **Step 3: Run the drift gate test**

Run: `.venv-test/bin/python -m pytest tests/test_fish_functions_installed.py -q`
Expected: 3 passed — the four new functions are linked, both sides match.

- [ ] **Step 4: Add the missing commands.json entry for stack-arr-search-toggle**

Edit `control-panel/static/commands.json` by hand, appending one entry before the closing `]`, matching the surrounding style exactly (2-space indent, key order as in neighbouring entries). Do not re-serialise the file.

```json
  {
    "Name": "stack-arr-search-toggle",
    "Description": "Toggle automatic search on or off for Radarr/Sonarr",
    "Method": "POST",
    "PathTemplate": "/api/arr/{1}/search-toggle",
    "Query": null,
    "Args": [
      {
        "Name": "radarr/sonarr",
        "Choices": ["radarr", "sonarr"],
        "Optional": false,
        "Default": "",
        "Rest": false
      }
    ],
    "Confirm": false,
    "BodyMode": "json",
    "BodyFields": [],
    "LogContainer": ""
  }
```

Before writing it, read `fish-functions/stack-arr-search-toggle.fish` and confirm the method, path and arguments above match what it actually calls. If they differ, the function is right and this entry is wrong — follow the function.

- [ ] **Step 5: Verify the JSON is still valid and unchanged elsewhere**

Run:
```bash
.venv-test/bin/python -c "import json; print(len(json.load(open('control-panel/static/commands.json'))))"
git diff --stat control-panel/static/commands.json
```
Expected: 136 entries, and a diff with insertions only — zero deletions. Any deletion means the file was re-serialised; revert and redo by hand.

- [ ] **Step 6: Commit**

```bash
git add fish-functions/stack-loop-candidates.fish fish-functions/stack-loop-unmonitor.fish \
        fish-functions/stack-loop-exclude.fish fish-functions/stack-nzbdav-dedup-check.fish \
        control-panel/static/commands.json
git commit -m "feat: write the 4 fish functions commands.json already advertised (Phase 8a)"
```

---

### Task 4: Correct the stale deployment comment in __stack_api

`__stack_api.fish` documents the old reality in a load-bearing comment: "this function is deployed as a plain copy at ~/.config/fish/functions/, not a symlink into the repo". After Task 2 that is false, and the next reader will trust it.

**Files:**
- Modify: `fish-functions/__stack_api.fish` (the comment block above `set -l env_file`)

**Interfaces:**
- Consumes: nothing. Produces: nothing. Comment-only change.

- [ ] **Step 1: Confirm the repo copy exists and matches the installed one**

Run: `diff ~/.config/fish/functions/__stack_api.fish fish-functions/__stack_api.fish`
Expected: no output. If the file is absent from `fish-functions/`, copy the installed one in first — `__stack_api` is not managed by the installer (it lacks the `stack-` prefix) but it must still be tracked.

- [ ] **Step 2: Replace the stale comment**

Old:

```fish
    # Hardcoded, not derived from status --current-filename - this function
    # is deployed as a plain copy at ~/.config/fish/functions/, not a
    # symlink into the repo (~/.dotfiles doesn't exist on this host as of
    # 2026-08-04), so a self-relative path would resolve to the wrong place.
```

New:

```fish
    # Hardcoded, not derived from the running file's location. Since Phase 8a
    # (2026-08-13) the stack-* functions ARE symlinks into this repo, but this
    # helper is not one of them - it has no stack- prefix, so
    # scripts/fish-functions-install.py does not manage it, and it stays a
    # plain copy. Keeping the path absolute means both arrangements resolve
    # to the same .env either way.
```

- [ ] **Step 3: Verify the helper still works**

Run: `fish -c 'stack-plex-libraries' | head -2`
Expected: a real answer. If `__stack_api` were broken, every `stack-*` command would fail at once.

- [ ] **Step 4: Commit**

```bash
git add fish-functions/__stack_api.fish
git commit -m "docs: correct __stack_api's deployment comment after the symlink cutover"
```

---

### Task 5: Close out Phase 8a

Proves 8a as a whole before 8b touches a single name.

**Files:**
- Modify: `PLANS.md` (Phase 8 section)

- [ ] **Step 1: Run the full suite**

Run: `.venv-test/bin/python -m pytest -q`
Expected: 834 passed (824 baseline + 7 installer + 3 drift). If the number is lower, find out why before continuing.

- [ ] **Step 2: Re-verify the live surface**

Run:
```bash
ls ~/.config/fish/functions/stack-*.fish | wc -l     # expect 194
ls fish-functions/stack-*.fish | wc -l               # expect 194
fish -c 'stack-status' | head -5
```
Expected: both counts equal (190 - 0 deleted from repo + 4 new = 194 both sides; the 5 pruned host files were never in the repo), and `stack-status` answers.

- [ ] **Step 3: Update PLANS.md Phase 8**

Change the Phase 8 `**Status:**` line to:

```markdown
**Status:** 8a DONE (2026-08-13) — integrity: symlink cutover, restic orphans
removed, missing functions written. 8b (the rename) IN PROGRESS. Full design
and decisions: `docs/superpowers/specs/2026-08-13-cli-naming-cleanup-design.md`,
which supersedes 8.2-8.4 below.
```

- [ ] **Step 4: Commit and push**

```bash
git add PLANS.md
git commit -m "docs: Phase 8a complete, 8b in progress"
git push
```

---

### Task 6: The naming linter — structural rules

Rules 1, 2 and 6 from the spec: filename matches declaration, domain is known, no bare-domain names. These are the rules with zero judgment in them, so they land first and must pass immediately on the current tree (no renames yet).

**Files:**
- Create: `tests/test_fish_naming.py`

**Interfaces:**
- Consumes: nothing.
- Produces: module-level constants that Task 7 extends — `SERVICE_DOMAINS: set[str]`, `HOST_DOMAINS: set[str]`, `SOURCE_FIRST_DOMAINS: set[str]`, `TOP_LEVEL_COMMANDS: set[str]`, and `_functions() -> list[tuple[str, Path]]` yielding `(name_without_stack_prefix, path)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fish_naming.py`:

```python
"""Phase 8b: the naming schema for this stack's fish commands, as a gate test.

This file is the schema. There is no prose document that can drift from it -
if a rule is not encoded here, it is not a rule, and the failure output of
these tests is the audit PLANS.md 8.4 asked for.

Two domain namespaces exist and both are legitimate: service commands, whose
domain is a container in docker-compose.yml, and host commands (disk, journal,
kernel, pkg...), which are not services at all. Conflating them was the real
inconsistency behind 66 distinct domain tokens across 190 functions.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_DIR = REPO_ROOT / "fish-functions"
COMPOSE = REPO_ROOT / "docker-compose.yml"

# Host-level concerns. Not services, deliberately not renamed - see the spec's
# decision 5. Adding a domain here is how a new host command becomes legal.
HOST_DOMAINS = {
    "aur", "backlog", "claude", "command", "container", "cron", "disk",
    "docker", "firewall", "flatpak", "git", "image", "journal", "kernel",
    "log", "mem", "mount", "newapps", "notify", "oom", "perms", "pkg",
    "queue", "reboot", "resource", "restart", "service", "ssh", "status",
    "timer", "top", "uptime", "version", "zombie",
}

# Named after the data source rather than the target app, kept as a documented
# exception - they read as intent and tab-complete by source. Spec decision 3.
SOURCE_FIRST_DOMAINS = {"imdb", "letterboxd", "mdblist", "tmdb", "trakt"}

# Bare names with no action, allowlisted as top-level entry points. Renaming
# the most-typed command in the stack for schema purity costs more than it
# returns.
TOP_LEVEL_COMMANDS = {"stack-status", "stack-container", "stack-help"}

# Domains that are real but whose container name does not match the token
# (e.g. the arr family is addressed as one domain with an app argument).
EXTRA_SERVICE_DOMAINS = {"arr", "customformat", "cutoff", "rating", "recently", "import"}


def _compose_services() -> set[str]:
    """Service names from docker-compose.yml, without parsing YAML - the file
    has anchors and merge keys that a naive loader chokes on, and this only
    needs the top-level keys under `services:`."""
    domains = set()
    in_services = False
    for line in COMPOSE.read_text().splitlines():
        if line.startswith("services:"):
            in_services = True
            continue
        if in_services and line and not line[0].isspace():
            break
        match = re.match(r"^  ([a-z0-9][a-z0-9_-]*):\s*$", line)
        if in_services and match:
            name = match.group(1)
            domains.add(name)
            # radarr-anime is reached as `stack-radarr-*` with an argument.
            domains.add(name.split("-")[0])
    return domains


SERVICE_DOMAINS = _compose_services() | EXTRA_SERVICE_DOMAINS


def _functions() -> list[tuple[str, Path]]:
    return [(path.stem, path) for path in sorted(REPO_DIR.glob("stack-*.fish"))]


def test_filename_matches_the_declared_function_name():
    """A mismatch means `stack-foo` runs code from stack-bar.fish - fish
    autoloads by filename, so the file wins and the declaration is a lie."""
    offenders = []
    for name, path in _functions():
        declared = re.search(r"^function\s+(\S+)", path.read_text(), re.MULTILINE)
        if not declared:
            offenders.append(f"{name}: no `function` declaration")
        elif declared.group(1) != name:
            offenders.append(f"{name}: declares `{declared.group(1)}`")
    assert not offenders, "\n  " + "\n  ".join(offenders)


def test_every_domain_is_known():
    """An unknown domain is usually a typo or an invented namespace. Adding a
    legitimate one means adding it to HOST_DOMAINS or a compose service."""
    known = SERVICE_DOMAINS | HOST_DOMAINS | SOURCE_FIRST_DOMAINS
    offenders = [name for name, _ in _functions()
                 if name not in TOP_LEVEL_COMMANDS and name.split("-")[1] not in known]
    assert not offenders, (
        "unknown domain in:\n  " + "\n  ".join(sorted(offenders)))


def test_no_bare_domain_names_outside_the_allowlist():
    """`stack-container` with no action is ambiguous; it is allowlisted only
    because it predates the schema and is typed constantly."""
    offenders = [name for name, _ in _functions()
                 if len(name.split("-")) == 2 and name not in TOP_LEVEL_COMMANDS]
    assert not offenders, "\n  " + "\n  ".join(sorted(offenders))
```

- [ ] **Step 2: Run it and read the failures**

Run: `.venv-test/bin/python -m pytest tests/test_fish_naming.py -q`
Expected: `test_every_domain_is_known` may fail with a handful of names. Each failure is a decision, not a bug in the test: either the domain is legitimate (add it to `HOST_DOMAINS`, with the reason in the commit message) or it is the first genuine violation. Do not add a domain to make a rename disappear — those belong in Task 8.

- [ ] **Step 3: Adjust the allowlists until the three tests pass**

Iterate: run, read the offender list, classify each. Expected end state: all three pass with no function renamed. If a name cannot be made legal without renaming it, note it and carry it into Task 8's rename map rather than widening the allowlist.

- [ ] **Step 4: Verify the linter actually catches a violation**

Run:
```bash
cp fish-functions/stack-plex-libraries.fish fish-functions/stack-bogusdomain-thing.fish
.venv-test/bin/python -m pytest tests/test_fish_naming.py -q   # expect 2 failures
rm fish-functions/stack-bogusdomain-thing.fish
```
Expected: `test_filename_matches_the_declared_function_name` and `test_every_domain_is_known` both fail, naming `stack-bogusdomain-thing`. A linter that has never been seen to fail is not known to work.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fish_naming.py
git commit -m "test: structural half of the fish naming schema (Phase 8b)"
```

---

### Task 7: Verb-order rules, the rename script, and the rename itself

Rules 3, 4, 5 and 7, plus the rename that satisfies them. These are one task because the rules describe the post-rename state: committing them alone would land a red test. Write the rules, read their output as the audit, build the script, run it, end green.

**Files:**
- Modify: `tests/test_fish_naming.py`
- Create: `scripts/fish-rename.py`
- Create: `tests/scripts/test_fish_rename.py`
- Modify: 12 files in `fish-functions/` (renamed), `control-panel/static/commands.json`, the `SKILL.md` files that reference old names, `README.md`, `STACK.md`, `AGENTS.md`

**Interfaces:**
- Consumes: `SERVICE_DOMAINS`, `HOST_DOMAINS`, `SOURCE_FIRST_DOMAINS`, `TOP_LEVEL_COMMANDS`, `_functions()` from Task 6.
- Produces: `VERBS: set[str]` and `NOUN_PHRASE_ALLOWLIST: set[str]`, used by nothing else.

- [ ] **Step 1: Append the rules to tests/test_fish_naming.py**

```python
# Action words this stack actually uses. A name whose action portion contains
# one of these must lead with it.
VERBS = {
    "add", "analyze", "apply", "backup", "check", "clean", "clear", "delete",
    "dedup", "diff", "empty", "exclude", "export", "find", "fix", "generate",
    "import", "install", "kill", "list", "monitor", "open", "process",
    "prune", "publish", "refresh", "remove", "repair", "reset", "restart",
    "restore", "run", "scan", "search", "show", "start", "stop", "sync",
    "tail", "test", "toggle", "track", "unmonitor", "unstick", "untrack",
    "update", "upgrade", "verify",
}

# Names whose trailing word is a verb by coincidence - they are noun phrases,
# not actions. "last-run" is a thing, not an instruction to run something.
NOUN_PHRASE_ALLOWLIST = {
    "stack-claude-full-backup",
    "stack-maintainerr-plex-link-check",
    "stack-maintainerr-safety-check",
    "stack-plexanisync-last-run",
    "stack-prefetcharr-plex-link-check",
    "stack-scrutiny-alert-test",
    "stack-wrapperr-tautulli-link-check",
}


def _action_tokens(name: str) -> list[str]:
    """The part after `stack-<domain>-`, with the source-first family's
    two-token domain (letterboxd-radarr, mdblist-radarr) accounted for."""
    parts = name.split("-")[1:]
    if parts[0] in SOURCE_FIRST_DOMAINS and len(parts) > 2 and parts[1] in SERVICE_DOMAINS:
        return parts[2:]
    return parts[1:]


def test_actions_are_verb_first():
    """`stack-arr-blocklist-clear` reads as a noun being modified;
    `stack-arr-clear-blocklist` reads as the instruction it is. Reads with no
    verb at all (stack-plex-libraries) are unaffected by this rule."""
    offenders = []
    for name, _ in _functions():
        if name in TOP_LEVEL_COMMANDS or name in NOUN_PHRASE_ALLOWLIST:
            continue
        tokens = _action_tokens(name)
        if len(tokens) < 2:
            continue
        if any(t in VERBS for t in tokens) and tokens[0] not in VERBS:
            offenders.append(name)
    assert not offenders, (
        "verb-last names (move the verb to the front):\n  " + "\n  ".join(sorted(offenders)))


def test_source_first_domains_stay_source_first():
    """Guards the exception in both directions: these must keep naming the
    source first, so a well-meaning later rename to stack-radarr-letterboxd-*
    fails here."""
    offenders = [name for name, _ in _functions()
                 if name.split("-")[1] in SERVICE_DOMAINS
                 and any(f"-{src}-" in name for src in SOURCE_FIRST_DOMAINS)]
    assert not offenders, (
        "source-first family must lead with the source:\n  " + "\n  ".join(sorted(offenders)))


def test_no_two_commands_describe_the_same_concept():
    """The concrete case this was written for: stack-recently-added,
    stack-plex-recently-added and stack-tautulli-recently-added. Three real
    commands, but the first does not say that its domain is the Arr apps."""
    concepts = {}
    for name, _ in _functions():
        tokens = _action_tokens(name)
        if not tokens:
            continue
        concepts.setdefault("-".join(tokens), []).append(name)
    offenders = []
    for concept, names in sorted(concepts.items()):
        undomained = [n for n in names if len(n.split("-")) == len(concept.split("-")) + 1]
        if len(names) > 1 and undomained:
            offenders.append(f"{concept}: {sorted(names)} - {undomained} has no domain")
    assert not offenders, "\n  " + "\n  ".join(offenders)
```

- [ ] **Step 2: Run it and capture the audit**

Run: `.venv-test/bin/python -m pytest tests/test_fish_naming.py -q 2>&1 | tee /tmp/naming-audit.txt`
Expected: `test_actions_are_verb_first` fails listing ~10 names, `test_no_two_commands_describe_the_same_concept` fails listing the `recently-added` trio. `test_source_first_domains_stay_source_first` passes.

Compare the offender list against the spec's rename table. If the linter names something the spec does not, decide: extend `NOUN_PHRASE_ALLOWLIST` (it is a noun phrase) or extend the rename map in Task 8 (it is a real violation). If the spec names something the linter misses, the rule is too narrow — widen `VERBS`.

Do not commit yet — the verb-order rules stay red until the rename below makes them green, and this task is not done until they are.

**Interfaces (rename script):**
- Consumes: `scripts/fish-functions-install.py` (called at the end).
- Produces: `RENAMES: dict[str, str]`, `rename_text(text: str, renames: dict[str, str]) -> str`, `targets(repo_root: Path) -> list[Path]`.

- [ ] **Step 4: Write the failing test for the rename script**

Create `tests/scripts/test_fish_rename.py`:

```python
"""Phase 8b: the rename script.

The case that makes this a script instead of sed: `stack-arr-import` is a
prefix of `stack-arr-import-all`, `stack-arr-import-backlog`,
`stack-arr-import-candidates` and `stack-arr-import-starvation`. A naive
substring replace turns stack-arr-import-all into <new-name>-all and silently
breaks four commands plus every doc that mentions them.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/fish-rename.py"


@pytest.fixture(scope="module")
def renamer():
    spec = importlib.util.spec_from_file_location("_script_fish_rename", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_script_fish_rename"] = module
    spec.loader.exec_module(module)
    return module


def test_exact_name_is_replaced(renamer):
    out = renamer.rename_text("run stack-arr-blocklist-clear now",
                              {"stack-arr-blocklist-clear": "stack-arr-clear-blocklist"})
    assert out == "run stack-arr-clear-blocklist now"


def test_longer_name_with_the_same_prefix_is_untouched(renamer):
    """The whole reason this file exists."""
    text = "stack-arr-import and stack-arr-import-all and stack-arr-import-backlog"
    out = renamer.rename_text(text, {"stack-arr-import": "stack-arr-pull"})
    assert out == "stack-arr-pull and stack-arr-import-all and stack-arr-import-backlog"


def test_name_inside_a_path_or_quotes_is_replaced(renamer):
    text = 'fish-functions/stack-plex-rss-import.fish and "stack-plex-rss-import"'
    out = renamer.rename_text(text, {"stack-plex-rss-import": "stack-plex-import-rss"})
    assert out == 'fish-functions/stack-plex-import-rss.fish and "stack-plex-import-rss"'


def test_name_as_part_of_a_longer_word_is_untouched(renamer):
    out = renamer.rename_text("xstack-plex-rss-importer",
                              {"stack-plex-rss-import": "stack-plex-import-rss"})
    assert out == "xstack-plex-rss-importer"


def test_multiple_renames_in_one_pass_do_not_cascade(renamer):
    """A -> B and B -> C must not turn A into C."""
    out = renamer.rename_text("stack-a stack-b", {"stack-a": "stack-b", "stack-b": "stack-c"})
    assert out == "stack-b stack-c"


def test_every_rename_target_is_a_new_name(renamer):
    """Guards the map itself: a typo that maps two old names onto the same new
    one would silently delete a command."""
    assert len(set(renamer.RENAMES.values())) == len(renamer.RENAMES)
    assert not set(renamer.RENAMES) & set(renamer.RENAMES.values())


def test_targets_include_every_reference_surface(renamer, tmp_path):
    (tmp_path / "fish-functions").mkdir()
    (tmp_path / "fish-functions/stack-x.fish").write_text("x")
    (tmp_path / "control-panel/static").mkdir(parents=True)
    (tmp_path / "control-panel/static/commands.json").write_text("[]")
    (tmp_path / ".claude/skills/demo").mkdir(parents=True)
    (tmp_path / ".claude/skills/demo/SKILL.md").write_text("x")
    for name in ("README.md", "STACK.md", "AGENTS.md", "PLANS.md"):
        (tmp_path / name).write_text("x")
    found = {p.name for p in renamer.targets(tmp_path)}
    assert {"stack-x.fish", "commands.json", "SKILL.md",
            "README.md", "STACK.md", "AGENTS.md", "PLANS.md"} <= found
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `.venv-test/bin/python -m pytest tests/scripts/test_fish_rename.py -q`
Expected: collection error — the script does not exist.

- [ ] **Step 6: Write the rename script**

Create `scripts/fish-rename.py`:

```python
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


def targets(repo_root: Path) -> list[Path]:
    """Every file that can name a command as a string."""
    found: list[Path] = []
    found.extend(sorted((repo_root / "fish-functions").glob("*.fish")))
    commands = repo_root / "control-panel/static/commands.json"
    if commands.is_file():
        found.append(commands)
    found.extend(sorted((repo_root / ".claude/skills").rglob("SKILL.md")))
    for name in ("README.md", "STACK.md", "AGENTS.md", "PLANS.md", "CLAUDE.md"):
        path = repo_root / name
        if path.is_file():
            found.append(path)
    return found


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
        if result.stdout.strip():
            leftovers.append(f"{old}:\n{result.stdout}")
    if leftovers:
        print("\nOLD NAMES STILL PRESENT:\n" + "\n".join(leftovers))
        return 1
    print("\nNo old names remain in tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `.venv-test/bin/python -m pytest tests/scripts/test_fish_rename.py -q`
Expected: 7 passed.

- [ ] **Step 8: Dry-run the rename and read every line**

Run: `.venv-test/bin/python scripts/fish-rename.py --dry-run`
Expected: an edit line per affected file plus 12 `git mv` lines. If a file you did not expect appears, read that diff before proceeding.

- [ ] **Step 9: Run it for real**

Run: `.venv-test/bin/python scripts/fish-rename.py`
Expected: exits 0 with "No old names remain in tracked files." If it exits 1, the listed references are in files `targets()` does not cover — add them there rather than editing by hand, so the coverage is permanent.

- [ ] **Step 10: Verify the linter is now green**

Run: `.venv-test/bin/python -m pytest tests/test_fish_naming.py -q`
Expected: 6 passed. This is the moment Task 7's deliberately-red tests turn green.

- [ ] **Step 11: Verify the live shell**

Run:
```bash
fish -c 'stack-arr-clear-blocklist' | head -2        # expect the usage error
fish -c 'stack-arr-recently-added' | head -3
fish -c 'stack-plex-import-watchlist' | head -3
fish -c 'stack-arr-blocklist-clear' 2>&1 | head -1   # expect "Unknown command"
```
Expected: the new names work and the old one is gone. Fish caches autoloaded functions per session, so run these in a fresh `fish -c`, not an interactive shell that has been open since before the rename.

- [ ] **Step 12: Run the full suite**

Run: `.venv-test/bin/python -m pytest -q`
Expected: 847 passed (834 after Task 5, + 3 structural + 3 verb/duplicate + 7 rename-script).

- [ ] **Step 13: Check the commands.json diff is surgical**

Run: `git diff --stat control-panel/static/commands.json`
Expected: equal insertions and deletions, roughly 10-14 lines, all of them `"Name"` values. Any change to an unrelated entry means the em-dash escaping problem recurred — revert that file and re-run with the script only.

- [ ] **Step 14: Commit**

```bash
git add -A
git commit -m "refactor: rename 12 fish commands to the enforced schema (Phase 8b)"
git push
```

---

### Task 8: Document the cleanup and close Phase 8

**Files:**
- Modify: `PLANS.md`, `STACK.md`

- [ ] **Step 1: Update PLANS.md Phase 8**

Set Phase 8's `**Status:**` to:

```markdown
**Status:** DONE (2026-08-13). 8a integrity + 8b rename both shipped. 12
commands renamed, schema enforced by `tests/test_fish_naming.py`. Design and
decisions: `docs/superpowers/specs/2026-08-13-cli-naming-cleanup-design.md`,
which supersedes 8.2-8.4 below.
```

- [ ] **Step 2: Add the STACK.md entry**

Append a dated entry covering: the two-source-of-truth drift that started this, the symlink invariant and where it is enforced, the 12 renames as a table, the domains that were deliberately NOT renamed (35 host + 21 source-first) and why, and the fact that `tests/test_fish_naming.py` is now the schema — a new function with a bad name fails at commit time.

- [ ] **Step 3: Commit and push**

```bash
git add PLANS.md STACK.md
git commit -m "docs: STACK.md entry and Phase 8 closeout for the CLI naming cleanup"
git push
```

---

## Self-Review

**Spec coverage.** Decision 1 (integrity first) → Tasks 1-5 before 6-9. Decision 2 (symlinks) → Tasks 1-2. Decision 3 (source-first kept) → Task 7's `test_source_first_domains_stay_source_first`. Decision 4 (endpoints frozen) → no task edits a route; stated in Global Constraints. Decision 5 (host domains allowlisted) → Task 6's `HOST_DOMAINS`. Decision 6 (hard cutover) → Task 8, no alias step anywhere. The 8a work items map to Tasks 2 (orphans, mdblist install, backups dir), 3 (4 missing functions, the `commands.json` gap), 1 and 2 (installer, gate test). All seven schema rules appear: rules 1/2/6 in Task 6, rules 3/4/5/7 in Task 7. The 12-row rename table is `RENAMES` in Task 8 verbatim. Both spec risks are addressed — the 12-name break is called out in Task 9 Step 4, the `commands.json` round-trip risk in Global Constraints and Task 9 Step 6.

**Gap found and closed:** the spec's testing section requires the prefix-collision test; it is Task 8 Step 1's `test_longer_name_with_the_same_prefix_is_untouched`.

**Gap found and closed:** nothing in the spec covered `__stack_api.fish`'s comment, which asserts the pre-cutover deployment model and would mislead the next reader. Added as Task 4.

**Type consistency.** `plan()`/`apply()` signatures match between Task 1's script and its test, including the `repo_dir` keyword the Step 3 note corrects. `_functions()`, `SERVICE_DOMAINS`, `HOST_DOMAINS`, `SOURCE_FIRST_DOMAINS` and `TOP_LEVEL_COMMANDS` are defined in Task 6 and used unchanged in Task 7. `RENAMES`, `rename_text()` and `targets()` match between Task 8's script and test.

**Counts.** 824 baseline → 834 after Task 5 (7 + 3) → 847 after Task 9 (+3 +3 +7). Function counts: 190 repo + 4 written = 194 both sides after Task 3, unchanged by Task 9 since renames are 1:1.
