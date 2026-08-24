# CLI naming cleanup — design

Date: 2026-08-13
Supersedes: PLANS.md Phase 8, sections 8.2–8.4, which were a pointer to this
spec rather than the spec itself.

## Problem

PLANS.md Phase 8 frames the work as a whole-stack rename: ~150 fish functions
with drifting verb order, renamed for consistency. Measuring the real surface
on 2026-08-13 contradicts that framing in two directions.

**The naming is more consistent than 8.3 implied.** Two conventions are already
dominant and mostly followed: actions are verb-first (`stack-plex-empty-trash`,
`stack-plex-refresh-libraries`, `stack-plex-generate-intro-markers`) and reads
are bare nouns (`stack-plex-libraries`, `stack-prowlarr-indexers`,
`stack-seerr-requests`). A mechanical verb-last scan across all 190 names
returns 18 candidates, of which most are noun phrases rather than violations
(`stack-plexanisync-last-run`, `stack-maintainerr-plex-link-check`,
`stack-claude-full-backup`). The genuine verb-order violations number 10.

**The surface has integrity problems the rename framing misses entirely.**
There are two sources of truth for fish functions — the repo's
`fish-functions/` and the host's `~/.config/fish/functions/` — and they have
already drifted apart in both directions. Renaming on top of that produces
three wrong copies rather than one right one.

### Measured current state (2026-08-13)

| Fact | Count |
|---|---|
| `stack-*` functions installed on the host | 191 |
| `stack-*` functions in the repo | 190 |
| Names present in only one of the two | 9 |
| Control-panel routes | 176 |
| `commands.json` entries | 135 |
| Installed functions with no `commands.json` entry | 60 (most local-only, at least 3 API-backed) |
| `commands.json` entries with no function anywhere | 4 |
| Distinct `stack-*` strings referenced in skills/README/STACK.md/AGENTS.md | 212 |
| Distinct domain tokens across 190 functions | 66 (39 of them singletons) |

Resolved by inspection, no decision needed:

- The 5 installed-only functions (`stack-backup-integrity-check`,
  `stack-backup-restore-test`, `stack-backup-status`, `stack-backup-verify`,
  `stack-newapps-backup-check`) are **restic orphans**. restic was removed on
  2026-08-12; all four routes they call now return 404, and
  `control-panel/services/backups/` is an empty directory left behind by that
  removal. They are dead and get deleted.
- The 4 repo-only functions (`stack-mdblist-radarr-{history,track,tracked,untrack}`)
  back live routes and were simply never installed.
- The 4 `commands.json` entries with no function
  (`stack-loop-{candidates,exclude,unmonitor}`, `stack-nzbdav-dedup-check`) are
  **not dead entries** — their routes are live (`/api/arr/{app}/loop-candidates`
  answers, `/api/arr/{app}/unmonitor` returns 422 on an empty body, i.e. exists).
  The fish functions were never written. They get created.

## Decisions

Locked during the 2026-08-13 brainstorm. The first four override or resolve
open questions in PLANS.md 8.2–8.4.

1. **Integrity first, then rename.** Two commits, strictly ordered: 8a makes
   the surface trustworthy, 8b renames. 8b does not start until 8a's gate test
   is green.
2. **One source of truth, enforced by symlink.** Every installed
   `~/.config/fish/functions/stack-*.fish` becomes a symlink into the repo's
   `fish-functions/`. Drift becomes structurally impossible rather than
   discouraged. This is the pattern the repo's systemd units already use
   (verified working when `systemd/plexanisync.{service,timer}` were installed
   the same day).
3. **The source-first family stays**, as a documented exception:
   `stack-letterboxd-radarr-*`, `stack-mdblist-radarr-*`, `stack-tmdb-*`,
   `stack-trakt-*`. They read as intent ("import my Letterboxd watchlist into
   Radarr") and tab-complete by source, which is how they are actually reached
   for. Normalizing them would bury 12 distinct commands under the same
   `stack-radarr-` prefix as 30 unrelated ones.
4. **Control-panel endpoints are frozen.** The fish layer is renamed; `/api/*`
   paths are not. Endpoints are addressed by machines, so consistency buys
   nothing there, while renaming them would break `commands.json`, 7 skill
   docs and the panel's own JS. They are already not 1:1 with functions (176
   vs 191); this decision drops the pretence that they mirror each other
   rather than trying to enforce it.
5. **Host domains are allowlisted, not renamed.** 35 of the 190 functions are
   host-level (`disk`, `journal`, `kernel`, `firewall`, `pkg`, `oom`,
   `docker`, `ssh`, …) rather than service commands. The linter accepts two
   domain sources — services in `docker-compose.yml`, plus an explicit
   host-domain allowlist — so the distinction is documented and enforced
   without renaming 35 frequently-typed commands.
6. **Hard cutover, no deprecated aliases**, carried forward unchanged from
   PLANS.md 8.2.

## Architecture

### Phase 8a — integrity

1. Delete the 5 restic-orphan functions from the host, and remove the empty
   `control-panel/services/backups/` directory.
2. Install the 4 `stack-mdblist-radarr-*` functions that exist only in the repo.
3. Write the 4 missing functions named in `commands.json`.
4. Add a `commands.json` entry for `stack-arr-search-toggle`. Three API-backed
   functions were found without entries, but two of them
   (`stack-backup-restore-test`, `stack-backup-verify`) are restic orphans
   deleted in step 1, so only this one is a real gap.
5. Add `scripts/fish-functions-install.py`: creates and repairs the symlinks,
   idempotent, safe to re-run.
6. Add `tests/test_fish_functions_installed.py`: every installed `stack-*`
   path is a symlink resolving into the repo, and the repo and installed name
   sets are identical.

### Phase 8b — rename

1. Add `tests/test_fish_naming.py`, the schema linter, with the domain
   allowlists as data at the top of the file. Its failure output is the audit
   artifact PLANS.md 8.4 asks for — derived from the rule rather than from
   eyeballing 190 names.
2. Add `scripts/fish-rename.py`: applies an old→new map across
   `fish-functions/`, `commands.json`, the 7 skill `SKILL.md` files, `README.md`,
   `STACK.md` and `AGENTS.md`, then re-runs the installer, then greps for each
   old name expecting zero hits outside git history.
3. Run it. Fix until the linter is green.

Both test files are gate-lane per CLAUDE.md: local, free, deterministic,
sub-2s, run on every commit.

## The schema

The linter encodes seven rules:

1. A function's filename matches the name in its `function <name>` declaration.
2. The domain token is on a known list: a service in `docker-compose.yml`, or
   a member of the explicit host-domain allowlist.
3. Action commands are verb-first: `stack-<domain>-<verb>-<object>`.
4. Read commands are bare nouns: `stack-<domain>-<noun>`.
5. The source-first family is allowlisted by domain prefix.
6. No bare-domain names, except `stack-status` and `stack-container`, which are
   allowlisted as deliberate top-level entry points.
7. No two functions describe the same concept for the same domain.

`stack-status` and `stack-container` are exempted on purpose. Renaming the
most-typed command in the stack for schema purity is a cost with no return.

## The rename list — 12 functions

Verb order (10):

| Old | New |
|---|---|
| `stack-arr-blocklist-clear` | `stack-arr-clear-blocklist` |
| `stack-arr-search-toggle` | `stack-arr-toggle-search` |
| `stack-plex-rss-import` | `stack-plex-import-rss` |
| `stack-plex-watchlist-import` | `stack-plex-import-watchlist` |
| `stack-radarr-list-import` | `stack-radarr-import-list` |
| `stack-sonarr-custom-list-import` | `stack-sonarr-import-custom-list` |
| `stack-sonarr-monitor-episodes-fix` | `stack-sonarr-fix-episode-monitoring` |
| `stack-tmdb-company-import` | `stack-tmdb-import-company` |
| `stack-tmdb-keyword-import` | `stack-tmdb-import-keyword` |
| `stack-trakt-list-import` | `stack-trakt-import-list` |

Domain clarity (2):

| Old | New | Why |
|---|---|---|
| `stack-recently-added` | `stack-arr-recently-added` | Not dead code competing with `stack-plex-recently-added`, as 8.3 assumed — it is the Radarr/Sonarr version with its domain missing from the name. All three of the "recently added" commands survive, correctly named. |
| `stack-disk-usage` | `stack-disk-config-sizes` | Reports per-app `config/` directory sizes, which is neither disk usage generally nor the same thing as `stack-docker-disk-usage`. |

## Testing

- `tests/test_fish_functions_installed.py` (8a): symlink invariant, set
  equality between repo and installed, no dangling links.
- `tests/test_fish_naming.py` (8b): the seven schema rules, one test per rule,
  each reporting every violating name rather than the first.
- `scripts/fish-rename.py` ships with its own test covering the multi-file
  replacement, including the case that matters — a name that is a prefix of
  another (`stack-arr-import` vs `stack-arr-import-all`) must not be corrupted
  by a naive substring replace.
- Migration proof: zero grep hits for any old name across the repo, run by the
  rename script, not by hand.

## Risks

- **The 12 old names break at once**, in any open shell after `exec fish`, and
  in any personal script or muscle memory referencing them. That is the
  intended consequence of the no-aliases decision, not a surprise — but 12 is
  the number of things to retrain.
- **The symlink cutover touches the live shell environment.** If the installer
  is wrong, functions disappear from a running session. Mitigation: it is
  idempotent and re-runnable, the gate test proves the end state, and the repo
  copy is never the thing deleted.
- **`commands.json` is edited by script.** It has 135 entries and a specific
  key schema (`Name`/`Query`/`Args` with `Literal`, `Choices`, `Optional`,
  `Default`, `Rest`). The rename script edits values, never re-serialises
  wholesale — a `json.dump` round-trip rewrote em-dashes as `—` escapes
  earlier today and had to be reverted.

## Out of scope

- Renaming control-panel endpoints (decision 4).
- Renaming host-domain commands (decision 5).
- The remaining local-only functions without `commands.json` entries — 60
  today, minus the 5 restic orphans and the one real gap above. They call no
  API and need no entry.
- Any change to `__stack_api` or the auth path.
