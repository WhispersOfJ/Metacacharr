# Control Panel: Maximalist Redesign + Service Catalog Expansion + Fish Launcher

**Date:** 2026-08-14
**Status:** Approved for planning
**Repo:** media-stack (control-panel/)

## Context

The control panel (`control-panel/`, FastAPI backend + vanilla JS/CSS frontend at
`control-panel/static/`) currently uses a restrained "technical spec-sheet"
aesthetic: glass cards, a stamp-grid header, muted accent colors, sparse
sparklines confined to the Plex Health rail. It has:

- A curated software catalog (`services/catalog/registry.py`, 21 entries,
  3 categories: Monitoring & observability, and others) with real
  image/tag/port/volume/env schemas, rendered by `static/js/catalog.js`
  as install/remove toggle cards via Docker SDK (not compose-file writes).
- A command palette (`static/commands.json`, 136 entries) mapping fish CLI
  commands to REST endpoints, driven by `static/js/palette.js`.
- 209 fish functions in `fish-functions/*.fish`, most (194) prefixed
  `stack-*`, only 136 of which have a palette/API mapping today.
- A rail-based single-page layout (`static/index.html`) with existing
  vitals/sparkline components on the Plex Health rail only.

This spec covers three changes that ship together against the same shell:

1. Redesign the visual language to a maximalist style (decorative shell +
   dense data visualization).
2. Expand the software catalog with 50+ new, individually-verified
   services across three new categories: Media, Browser Games, RetroArch
   Emulation.
3. Add a dedicated rail exposing every one of the 209 fish functions as a
   button with help text, wired to real execution where an API mapping
   exists.

## Goals / Non-goals

**Goals**
- Visually louder shell (color, type contrast, layered depth, texture)
  while keeping the existing industrial/technical identity recognizable.
- Raise data density across existing rails using more instances of the
  existing sparkline/vitals pattern, not a new charting framework.
- 50+ genuinely deployable services with verified (not fabricated)
  image, tag, ports, environment variables, and volume mappings.
- Every fish function is visible and self-documenting from the UI.
- No change to how installs actually happen (Docker SDK, not compose
  writes) and no change to the palette/command execution model.

**Non-goals**
- No new backend framework, build step, or JS bundler — stays vanilla
  ES modules + FastAPI, matching current architecture.
- No auto-configuration of catalog services into the Arr fleet.
- No fabricated env/volume schemas — anything unverifiable gets a
  narrower entry or is left out, never guessed.
- No internet exposure changes for any service.

## Part 1: Maximalist visual redesign

**Direction:** decorative shell + dense viz content (both, per approved
design). The existing token system (`--accent`, `--ink`, `--good`, etc.
in `style.css`) is extended, not replaced.

**Shell changes**
- New CSS custom properties for a wider, bolder palette: distinct hue
  per rail/category (Plex Health, Fleet, Host, Catalog, Fish Toolkit each
  get a signature accent), used consistently in headers, borders, and
  active states.
- Background texture/pattern layer behind `#workspace` (subtle grid,
  grain, or diagonal hatch consistent with the existing "stamp sheet"
  drafting-table motif — extending `.stampgrid` rather than introducing
  an unrelated motif).
- Typographic contrast: larger/heavier rail headings (`h2`), tighter
  mono HUD labels — widen the existing scale rather than add new font
  families (perf budget: max two families, already satisfied).
- Layered card depth: extend `.glass-card` with a stronger shadow/border
  treatment; distinguish catalog cards, vital cards, and fish-toolkit
  cards by accent color per category, not just by content.
- Dark/light theme toggle (`#theme-switch`) continues to drive both
  variants; every new token gets a light and dark value.

**Density changes**
- Multiply the existing sparkline pattern (`.sparkline-row`,
  `.sparkline-block`, SVG line+fill) from Plex Health-only into Fleet
  (per-container CPU/mem trend) and Host (existing `host-resources`
  gets sparkline history, not just instantaneous numbers).
- Catalog rail gains a summary strip: count of installed vs. available
  per category, small bar/heatmap of category footprint.
- Fish Toolkit rail (Part 3) is itself a density move — 209 buttons
  grouped and scannable, not just a change to feel busier for its own
  sake.
- No new chart library — everything renders as inline SVG the same way
  `.sparkline` already does, keeping the JS bundle-free.

**Testing**
- Visual regression screenshots at 320/768/1024/1440 in both themes
  (matches existing web-testing rule) before/after, reviewed manually
  since this project has no existing screenshot-diff tooling.
- Manual keyboard-nav and Ctrl+K palette smoke test after CSS changes,
  since layered z-index changes are the most likely regression source.

## Part 2: Service catalog expansion

**Schema:** unchanged. Every new entry follows the exact shape already
in `registry.py`:

```python
{
    "id": str, "name": str, "category": str, "pitch": str,
    "image": str, "tag": str,
    "ports": {"<container>/tcp": <host_port>},
    "volumes": {"<named_volume>": {"bind": "<path>", "mode": "rw"}},
    "environment": {...}, "cap_add": [...], "devices": [...],
    "footprint": str, "doc_url": str, "caveat": str | None,
}
```

**New categories:** `Media`, `Browser Games`, `RetroArch Emulation` —
roughly 17 services each, 50+ total. Selection criteria: established,
actively-maintained images (LinuxServer.io preferred where available),
ranked by the existing project convention (stars/recency/community
activity), each individually verified against its real Docker
Hub/GitHub/LinuxServer.io listing before being written into
`registry.py` — same rigor as the current 21 entries' provenance
comment at the top of the file.

**Research execution:** 3 parallel background research agents, one per
category, each producing verified `registry.py`-shaped entries for its
~17 services (image, tag, ports, env vars, volumes, footprint, doc URL,
caveat). I select the specific candidate services (well-known images,
not user-specified) and review/merge each agent's output before it's
written to `registry.py` — nothing lands unverified.

Port allocation: new entries must not collide with existing
`docker-compose.yml` or catalog ports; the implementation plan includes
a port-collision check step before finalizing entries.

**Card UI — surfacing env vars and volumes:**
`catalog.js`'s `renderCard()` currently shows name, pitch, caveat,
footprint, and ports, but not environment variables or volume mappings
even though the backend schema already carries them. Add a collapsible
"Details" section per card (button toggles a hidden block) listing:
- Environment variables as `KEY: value` (or `KEY: <required, set on
  install>` for secrets not hardcoded)
- Volume mappings as `named_volume → container_path`

This is an additive UI change to `catalog.js` + `style.css`; no backend
API shape change since `/api/catalog` already returns the full item
including `environment`/`volumes` (confirm during implementation —
if the router currently strips these fields for the list response,
extend it to include them).

**Testing**
- Gate test: `registry.py` entries validate against a schema check
  (required keys present, no port collisions, no duplicate ids) —
  extends whatever test coverage currently exists for the catalog
  service.
- Manual install/remove smoke test on at least one new entry per
  category through the live UI.

## Part 3: Fish function launcher

**New rail:** "Fish Toolkit", added to `index.html` alongside existing
rails, grouped by naming prefix (mirrors the existing `stack-*`
convention — e.g. group by first hyphen-segment: `stack-arr-*`,
`stack-plex-*`, `stack-letterboxd-*`, etc.) so 209 buttons are scannable
rather than one flat list.

**Help text source:** parsed from each `.fish` file, in priority order:
1. `function <name> -d "..."` inline description, if present.
2. Leading comment block immediately before the `function` line, if no
   `-d`.
3. If neither exists, the button shows "No description available" —
   flagged in the implementation plan's output so gaps are visible, not
   silently blank.

**Wiring — real execution vs. reference-only:**
Cross-reference all 209 function names against `commands.json`'s 136
`Name` entries.
- **Matched (136):** button opens the existing command palette flow
  pre-selected to that command (reuses `palette.js`'s arg-collection /
  confirm / run screens — no new execution path).
- **Unmatched (~73):** button is disabled/styled as reference-only,
  showing the fish invocation signature (name + args) to copy, plus its
  parsed help text. No fabricated API endpoint is created for these.

**Data source:** a small backend endpoint (or static generation step at
build/deploy time — decide in implementation planning) that parses
`fish-functions/*.fish` and returns
`[{name, description, has_api_mapping, command_name?}]`. Given 209
files, parsing at request time is cheap (regex over comments); no need
for a build step or caching layer.

**Testing**
- Gate test: parser correctly extracts `-d` description and
  comment-block fallback on a handful of representative fixture
  functions (one with `-d`, one with only a comment block, one with
  neither).
- Manual check that all 209 functions render, matched ones execute
  through the palette, unmatched ones show copyable signatures.

## File-level impact summary

| File | Change |
|---|---|
| `control-panel/static/style.css` | New tokens, texture layer, card/heading treatments, sparkline reuse styles |
| `control-panel/static/index.html` | New Fish Toolkit rail; catalog rail category labels for Media/Browser Games/RetroArch |
| `control-panel/static/js/catalog.js` | Add collapsible env/volume detail section per card |
| `control-panel/services/catalog/registry.py` | +50-ish verified entries, 3 new categories |
| `control-panel/services/catalog/router.py` | Confirm/extend `/api/catalog` to return env/volumes in list response |
| `control-panel/static/js/fleet.js` / `host.js` | Add sparkline history where only instantaneous values render today |
| New: `control-panel/static/js/fish-toolkit.js` | Render grouped fish-function buttons |
| New: backend fish-function parser (location TBD in implementation plan) | Parse `.fish` files → `{name, description, has_api_mapping}` |

## Open items for implementation planning (not blocking spec approval)

- Exact list of 50+ services per category (produced by the 3 research
  agents, reviewed before merge).
- Whether fish-function parsing happens as a FastAPI endpoint or a
  generated static JSON (like `commands.json`) refreshed on deploy.
- Exact port assignments for new catalog entries (collision-checked
  against `docker-compose.yml` + existing catalog).
