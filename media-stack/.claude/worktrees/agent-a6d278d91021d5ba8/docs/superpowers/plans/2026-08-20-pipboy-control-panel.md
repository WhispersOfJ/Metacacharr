# Pip-Boy Control Panel Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-theme the control panel as a Fallout Pip-Boy CRT terminal (amber/green palettes), promote Poster Sync from a hidden modal to the first always-visible rail, and remove the Software Catalog rail from the UI.

**Architecture:** Pure frontend change to a no-build-step, no-bundler static site (`control-panel/static/`) — ES modules loaded natively, CSS custom-property token swap driven by `document.documentElement.dataset.theme`, vanilla `node --test` for unit tests. Two tiny Python default-value edits in the settings backend, no schema/route changes.

**Tech Stack:** Vanilla JS (ES modules), CSS custom properties, `node:test` runner, Python (FastAPI-adjacent settings module, no framework changes needed).

**Spec:** `docs/superpowers/specs/2026-08-20-pipboy-control-panel-design.md`

## Global Constraints

- No external font/CDN fetches — self-hosted or system font stack only (repo's no-CDN habit).
- Theme values are exactly `"amber"` and `"green"` (replacing `"dark"`/`"light"`) — used verbatim in JS, CSS `[data-theme]` selectors, and both Python `DEFAULTS` dicts.
- No backend catalog API/route removal in this pass — `services/catalog/router.py` is untouched.
- Test command: `cd control-panel/static/js && node --test *.test.js` — baseline is 8 passing tests, 0 failures. Must stay green throughout.
- Manual verification requires a hard reload (`Ctrl+Shift+R`) after any static-file change, per this repo's standing control-panel verification rule — a plain restart is not sufficient to bust the browser cache.
- Every `.rail[data-rail-accent="X"]` in `index.html` must have a matching `--rail-X` CSS variable defined in all three of: base `:root`, the `prefers-color-scheme: dark` block, and the explicit `:root[data-theme="..."]` blocks in `style.css`. Removing or adding a rail means updating all three plus the `--rail-X` mapping rule.

---

## File Structure

| File | Change |
|---|---|
| `control-panel/static/index.html` | Rail reorder, poster-dock markup relocated into new `#rail-poster-sync`, `#rail-catalog` deleted, theme-switch label updated, `catalog.js` script include removed |
| `control-panel/static/style.css` | Amber/green palette tokens replace dark/light; CRT scanline/vignette/glow effects added; `--rail-catalog` and its mapping rule removed; `--rail-poster-sync` added |
| `control-panel/static/js/settings.js` | `applyTheme`/theme-switch handler use `amber`/`green` instead of `dark`/`light` |
| `control-panel/static/js/poster-sync.js` | `buildPosterDock` (modal-close wrapper) deleted; `buildPosterSync` exported and called directly |
| `control-panel/static/js/host.js` | "Poster sync — Open" row removed from Fleet-wide actions (redundant now that the rail is always visible) |
| `control-panel/static/js/catalog.js` | Deleted |
| `control-panel/static/app.js` | Import/call updated: `buildPosterDock` → `buildPosterSync`, `buildCatalog` import and call removed |
| `control-panel/core/settings.py` | `DEFAULTS["theme"]` — `"dark"` → `"amber"` |
| `control-panel/settings_store.py` | `DEFAULTS["theme"]` — `"dark"` → `"amber"` |

No new files. No test files added (no new logic — DOM relocation, CSS, and default-value changes only). Existing `core.test.js` / `fleet.test.js` / `sparkline.test.js` are the regression gate.

---

## Task 1: Backend theme default

**Files:**
- Modify: `control-panel/core/settings.py:14`
- Modify: `control-panel/settings_store.py:17`

**Interfaces:**
- Consumes: nothing
- Produces: `get_settings()["theme"]` now defaults to `"amber"` for both modules — Task 2/3's frontend code will read this value as-is (no parsing/mapping needed, it's an opaque string round-tripped through `/api/settings`).

- [ ] **Step 1: Change the default in `core/settings.py`**

In `control-panel/core/settings.py`, line 14, change:
```python
DEFAULTS = {
    "theme": "dark",
```
to:
```python
DEFAULTS = {
    "theme": "amber",
```

- [ ] **Step 2: Change the default in `settings_store.py`**

In `control-panel/settings_store.py`, line 17, change:
```python
DEFAULTS = {
    "theme": "dark",
```
to:
```python
DEFAULTS = {
    "theme": "amber",
```

- [ ] **Step 3: Verify no other Python code assumes `"dark"`/`"light"`**

Run:
```bash
grep -rn '"dark"\|'"'"'dark'"'"'\|"light"\|'"'"'light'"'"'' /home/bear/Claude/media-stack/control-panel --include="*.py"
```
Expected: no output (both files already edited, nothing else references these string literals).

- [ ] **Step 4: Commit**

```bash
cd /home/bear/Claude/media-stack
git add control-panel/core/settings.py control-panel/settings_store.py
git commit -m "feat: default control-panel theme to amber Pip-Boy palette"
```

---

## Task 2: Theme CSS — amber/green Pip-Boy palettes + CRT effects

**Files:**
- Modify: `control-panel/static/style.css:1-114` (palette tokens block)
- Modify: `control-panel/static/style.css:117-119` (add CRT base rules near `html, body`)
- Modify: `control-panel/static/style.css:156-169` (rail accent mapping — remove catalog, add poster-sync)
- Modify: `control-panel/static/style.css:253-269` (`.switch` — no structural change needed, palette tokens cascade automatically, verify visually in Task 6)

**Interfaces:**
- Consumes: nothing (CSS-only; token names below are what Tasks 4/5's JS reads/writes via `dataset.theme`)
- Produces: `:root[data-theme="amber"]` and `:root[data-theme="green"]` selectors, plus a `prefers-color-scheme: dark` fallback defaulting to amber (matches the existing pattern where the media-query fallback mirrors one explicit theme). `--rail-poster-sync` variable for the new rail's accent color.

- [ ] **Step 1: Replace the theme comment header**

In `control-panel/static/style.css`, replace lines 1-12:
```css
/* Control Panel — operator console for The Stack.
   Dark-glass redesign (2026-08-07): frosted panels floating over a near-
   black ground, one violet accent doing all the signaling work, soft
   depth instead of ruled hairlines. Every selector below kept its name
   from the previous "P&ID blueprint" pass on purpose — every JS view
   module targets these same classes, so this is a full re-skin with zero
   markup changes required anywhere else in the app. Letterboxd's block
   near the bottom is the one exception: it gets deliberately redesigned,
   not just recolored, matching the individual attention it got when it
   was first built.
   Theme is persisted server-side (see settings_store.py) and applied via
   [data-theme] rather than left to prefers-color-scheme alone. */
```
with:
```css
/* Control Panel — operator console for The Stack.
   Pip-Boy CRT redesign (2026-08-20): amber/green monochrome terminal,
   scanline + vignette overlay, glowing live values, beveled chunky
   panel borders, monospace throughout. Every selector below kept its
   name from the prior dark-glass pass on purpose — every JS view module
   targets these same classes, so this is a full re-skin with zero
   markup changes required anywhere else in the app except the
   poster-sync/catalog rail moves covered elsewhere in this plan.
   Theme is persisted server-side (see core/settings.py) and applied via
   [data-theme] rather than left to prefers-color-scheme alone. Two
   values only: "amber" and "green" — no light mode. */
```

- [ ] **Step 2: Replace the base `:root` token block**

Replace lines 14-52 (the base `:root { ... }` block) with:
```css
:root {
  --bg: #0a0805;
  --surface: #120d08;
  --surface-2: #1a130b;
  --glass: rgba(255, 176, 0, 0.04);
  --glass-strong: rgba(255, 176, 0, 0.08);
  --glass-border: rgba(255, 176, 0, 0.22);
  --line: rgba(255, 176, 0, 0.16);
  --line-strong: rgba(255, 176, 0, 0.32);
  --ink: #ffb000;
  --ink-soft: #cc8d00;
  --ink-faint: #8a6100;
  --accent: #ffb000;
  --accent-hover: #ffc94d;
  --accent-ink: #0a0805;
  --accent-tint: rgba(255, 176, 0, 0.10);
  --accent-tint-strong: rgba(255, 176, 0, 0.20);
  --good: #ffb000;
  --good-tint: rgba(255, 176, 0, 0.14);
  --warn: #ff8c00;
  --warn-tint: rgba(255, 140, 0, 0.14);
  --bad: #ff3b1f;
  --bad-tint: rgba(255, 59, 31, 0.14);
  --unknown: #8a6100;
  --rail-plex-health: #ffb000;
  --rail-overview: #ffb000;
  --rail-fleet: #ffb000;
  --rail-host: #ffb000;
  --rail-poster-sync: #ffb000;
  --rail-reference: #cc8d00;
  --radius: 2px;
  --radius-sm: 1px;
  --blur: 0px;
  --font-ui: "Share Tech Mono", ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", "JetBrains Mono", Consolas, monospace;
  --font-mono: "Share Tech Mono", ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", "JetBrains Mono", Consolas, monospace;
  --font-label: var(--font-mono);
  --log-w: 380px;
  --topbar-h: 58px;
  --crt-glow: 0 0 6px currentColor;
}
```
Note: `--radius`/`--blur` shrink toward zero and `--font-ui` switches to the mono stack — Pip-Boy UI has no rounded glass cards, everything is monospace. `"Share Tech Mono"` is listed first but the stack falls through to system monospace fonts since no font file is bundled (no CDN fetch, per Global Constraints) — this is a deliberate soft-preference, not a hard dependency.

- [ ] **Step 3: Replace the `prefers-color-scheme` fallback block**

Replace lines 54-86:
```css
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #131018;
    ...
  }
}
```
with:
```css
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="green"]) {
    /* Fallback mirrors the amber theme's values from :root above —
       amber is the default Pip-Boy palette when no explicit
       [data-theme] is set yet (e.g. before initSettings() runs). */
  }
}
```
This block can be empty since amber's values now live in the base `:root` directly (Step 2) — the base tokens ARE the amber palette, so no override is needed for the "system prefers dark, no explicit theme set" case. Delete the block's body but keep the media-query wrapper as a documented no-op comment, matching the file's existing habit of explaining non-obvious empty states.

- [ ] **Step 4: Replace the explicit `[data-theme="dark"]` block with `[data-theme="amber"]`**

Replace lines 87-100:
```css
:root[data-theme="dark"] {
  --bg: #131018; --surface: #1a1722; --surface-2: #221e2e;
  ...
  --rail-plex-health: #f0964a; --rail-overview: #a996ff; --rail-fleet: #4fd1d8; --rail-host: #4fb8e8; --rail-catalog: #e0a854; --rail-reference: #837c9c;
}
```
with:
```css
:root[data-theme="amber"] {
  --bg: #0a0805; --surface: #120d08; --surface-2: #1a130b;
  --glass: rgba(255, 176, 0, 0.04); --glass-strong: rgba(255, 176, 0, 0.08);
  --glass-border: rgba(255, 176, 0, 0.22);
  --line: rgba(255, 176, 0, 0.16); --line-strong: rgba(255, 176, 0, 0.32);
  --ink: #ffb000; --ink-soft: #cc8d00; --ink-faint: #8a6100;
  --accent: #ffb000; --accent-hover: #ffc94d; --accent-ink: #0a0805;
  --accent-tint: rgba(255, 176, 0, 0.10); --accent-tint-strong: rgba(255, 176, 0, 0.20);
  --good: #ffb000; --good-tint: rgba(255, 176, 0, 0.14);
  --warn: #ff8c00; --warn-tint: rgba(255, 140, 0, 0.14);
  --bad: #ff3b1f; --bad-tint: rgba(255, 59, 31, 0.14);
  --unknown: #8a6100;
  --rail-plex-health: #ffb000; --rail-overview: #ffb000; --rail-fleet: #ffb000; --rail-host: #ffb000; --rail-poster-sync: #ffb000; --rail-reference: #cc8d00;
}
```

- [ ] **Step 5: Replace the `[data-theme="light"]` block with `[data-theme="green"]`**

Replace lines 101-114 (the `:root[data-theme="light"] { ... }` block — read the file to get its exact current closing content, it runs to approximately line 116) with:
```css
:root[data-theme="green"] {
  --bg: #050a05; --surface: #0b120b; --surface-2: #101a10;
  --glass: rgba(51, 255, 51, 0.04); --glass-strong: rgba(51, 255, 51, 0.08);
  --glass-border: rgba(51, 255, 51, 0.22);
  --line: rgba(51, 255, 51, 0.16); --line-strong: rgba(51, 255, 51, 0.32);
  --ink: #33ff33; --ink-soft: #29cc29; --ink-faint: #1c8a1c;
  --accent: #33ff33; --accent-hover: #7dff7d; --accent-ink: #050a05;
  --accent-tint: rgba(51, 255, 51, 0.10); --accent-tint-strong: rgba(51, 255, 51, 0.20);
  --good: #33ff33; --good-tint: rgba(51, 255, 51, 0.14);
  --warn: #a0ff33; --warn-tint: rgba(160, 255, 51, 0.14);
  --bad: #ff5533; --bad-tint: rgba(255, 85, 51, 0.14);
  --unknown: #1c8a1c;
  --rail-plex-health: #33ff33; --rail-overview: #33ff33; --rail-fleet: #33ff33; --rail-host: #33ff33; --rail-poster-sync: #33ff33; --rail-reference: #29cc29;
}
```

- [ ] **Step 6: Update rail accent mapping — remove catalog, add poster-sync**

Find (originally around line 163-168, now shifted by prior edits — search for the literal text):
```css
.rail[data-rail-accent="plex-health"] { --rail-accent: var(--rail-plex-health); }
.rail[data-rail-accent="overview"] { --rail-accent: var(--rail-overview); }
.rail[data-rail-accent="fleet"] { --rail-accent: var(--rail-fleet); }
.rail[data-rail-accent="host"] { --rail-accent: var(--rail-host); }
.rail[data-rail-accent="catalog"] { --rail-accent: var(--rail-catalog); }
.rail[data-rail-accent="reference"] { --rail-accent: var(--rail-reference); }
```
Replace with:
```css
.rail[data-rail-accent="poster-sync"] { --rail-accent: var(--rail-poster-sync); }
.rail[data-rail-accent="plex-health"] { --rail-accent: var(--rail-plex-health); }
.rail[data-rail-accent="overview"] { --rail-accent: var(--rail-overview); }
.rail[data-rail-accent="fleet"] { --rail-accent: var(--rail-fleet); }
.rail[data-rail-accent="host"] { --rail-accent: var(--rail-host); }
.rail[data-rail-accent="reference"] { --rail-accent: var(--rail-reference); }
```

- [ ] **Step 7: Add CRT scanline/vignette/glow base rules**

Find the `body { ... }` rule (starts at line 119, ends at line 132 with the closing brace before `a { color: var(--ink); ...`). Immediately after that closing `}`, insert:
```css

/* Pip-Boy CRT effects — theme-independent, layered once over the whole
   viewport. Scanlines use a repeating gradient; the vignette darkens
   toward the edges; both are pointer-events:none so they never block
   interaction. */
body::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: 9999;
  pointer-events: none;
  background: repeating-linear-gradient(
    to bottom,
    rgba(0, 0, 0, 0.15) 0px,
    rgba(0, 0, 0, 0.15) 1px,
    transparent 1px,
    transparent 3px
  );
  mix-blend-mode: multiply;
}
body::after {
  content: "";
  position: fixed;
  inset: 0;
  z-index: 9998;
  pointer-events: none;
  background: radial-gradient(
    ellipse at center,
    transparent 55%,
    rgba(0, 0, 0, 0.35) 100%
  );
}
.rail h2, .vital-value, #clock, #uptime {
  text-shadow: var(--crt-glow);
}
.rail {
  border-radius: var(--radius);
  border: 1px solid var(--line-strong);
}
```

- [ ] **Step 8: Update the second `prefers-color-scheme` block (select-arrow styling, lines 393-400)**

This block styles the `<select>` dropdown arrow SVG and currently hardcodes the violet fill color `%23a996ff` (`#a996ff`), which no longer exists in the new palette. Find:
```css
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) select {
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23a996ff'/%3E%3C/svg%3E");
  }
}
:root[data-theme="dark"] select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23a996ff'/%3E%3C/svg%3E");
}
```
Replace with:
```css
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="green"]) select {
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23ffb000'/%3E%3C/svg%3E");
  }
}
:root[data-theme="amber"] select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23ffb000'/%3E%3C/svg%3E");
}
:root[data-theme="green"] select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2333ff33'/%3E%3C/svg%3E");
}
```
Note this adds a third rule (`[data-theme="green"] select`) since green needs its own arrow color — the original only had one explicit override because light mode used the default (non-dark-media-query) `select` rule at line 386, which is unaffected here.

- [ ] **Step 9: Verify no stray `--rail-catalog` or `[data-theme="dark"]`/`[data-theme="light"]` references remain**

Run:
```bash
grep -n 'rail-catalog\|data-theme="dark"\|data-theme="light"' /home/bear/Claude/media-stack/control-panel/static/style.css
```
Expected: no output.

- [ ] **Step 10: Commit**

```bash
cd /home/bear/Claude/media-stack
git add control-panel/static/style.css
git commit -m "feat: replace dark/light theme with amber/green Pip-Boy CRT palette"
```

---

## Task 3: HTML restructure — poster sync promotion, rail reorder, catalog removal

**Files:**
- Modify: `control-panel/static/index.html`

**Interfaces:**
- Consumes: `--rail-poster-sync` CSS variable and `.rail[data-rail-accent="poster-sync"]` selector from Task 2.
- Produces: `#rail-poster-sync` section containing the poster-dock markup (same element IDs as before: `poster-sync-form`, `poster-sync-library`, `poster-sync-source`, `poster-sync-mode`, `poster-sync-dry-run-wrap`, `poster-sync-dry-run`, `poster-sync-summary`, `poster-log`, `poster-review-grid`, `poster-gallery`, `poster-gallery-scan`, `poster-gallery-scan-summary`, `poster-gallery-grid`, `poster-gallery-prev`, `poster-gallery-page-info`, `poster-gallery-next`) — Task 4 (`poster-sync.js`) reads these same IDs, so IDs must be preserved exactly, only their container and `hidden` state change.

- [ ] **Step 1: Update the theme-switch label**

In `control-panel/static/index.html`, replace lines 37-41:
```html
    <label class="switch" title="Toggle dark/light theme">
      <input type="checkbox" id="theme-switch">
      <span class="switch-track"></span>
      <span class="switch-label">Dark</span>
    </label>
```
with:
```html
    <label class="switch" title="Toggle amber/green Pip-Boy palette">
      <input type="checkbox" id="theme-switch">
      <span class="switch-track"></span>
      <span class="switch-label">Amber</span>
    </label>
```
(Task 4 wires the label text to update dynamically the same way it does today — this static default just needs to match the new vocabulary.)

- [ ] **Step 2: Move poster-dock markup into a new rail, remove `hidden`, reorder ahead of Plex Health**

Replace the opening of `#col-main` — find:
```html
  <div id="col-main">

    <section class="rail" id="rail-plex-health" data-rail-accent="plex-health" aria-labelledby="h-plex-health">
```
with:
```html
  <div id="col-main">

    <section class="rail" id="rail-poster-sync" data-rail-accent="poster-sync" aria-labelledby="h-poster-sync">
      <h2 id="h-poster-sync">Poster Sync</h2>
      <form class="poster-sync-form" id="poster-sync-form">
        <label>Library
          <select id="poster-sync-library"><option value="">Loading libraries…</option></select>
        </label>
        <label>Source
          <select id="poster-sync-source">
            <option value="tmdb">TMDb</option>
            <option value="fanart">Fanart.tv</option>
            <option value="tvdb">TheTVDB</option>
            <option value="omdb">OMDb</option>
            <option value="tvmaze">TVmaze (shows only)</option>
          </select>
        </label>
        <label>Mode
          <select id="poster-sync-mode">
            <option value="auto">Auto (apply top match)</option>
            <option value="review">Review (pick top 3 per item)</option>
            <option value="gallery">Gallery (browse + quality scan)</option>
          </select>
        </label>
        <label class="poster-sync-check" id="poster-sync-dry-run-wrap">
          <input type="checkbox" id="poster-sync-dry-run">
          Dry run
        </label>
        <button class="btn-primary" type="submit">Start</button>
        <span class="hint" id="poster-sync-summary"></span>
      </form>
      <pre id="poster-log"></pre>
      <div class="poster-review-grid" id="poster-review-grid" hidden></div>
      <div class="poster-gallery" id="poster-gallery" hidden>
        <div class="poster-gallery-toolbar">
          <button class="btn-ghost" type="button" id="poster-gallery-scan">Run quality scan</button>
          <span class="hint" id="poster-gallery-scan-summary"></span>
        </div>
        <div class="poster-gallery-grid" id="poster-gallery-grid"></div>
        <div class="poster-gallery-pager">
          <button class="btn-ghost" type="button" id="poster-gallery-prev">&larr; Prev</button>
          <span class="hint" id="poster-gallery-page-info"></span>
          <button class="btn-ghost" type="button" id="poster-gallery-next">Next &rarr;</button>
        </div>
      </div>
    </section>

    <section class="rail" id="rail-plex-health" data-rail-accent="plex-health" aria-labelledby="h-plex-health">
```
Note: the old `.poster-dock-head` (with its "Poster sync" label and Close button) is dropped entirely — the rail's own `<h2>` replaces that header, and there's no close button since the rail is permanent, not dismissable.

- [ ] **Step 3: Delete the old bottom-of-body `#poster-dock` block**

Delete this entire block (originally lines 241-287, now shifted — search for the literal opening tag):
```html
<div class="poster-dock" id="poster-dock" hidden>
  ...
</div>
```
Delete from `<div class="poster-dock" id="poster-dock" hidden>` through its matching closing `</div>`, inclusive. Verify with:
```bash
grep -n 'poster-dock' /home/bear/Claude/media-stack/control-panel/static/index.html
```
Expected: no output (all references removed — the class/ID no longer exists anywhere).

- [ ] **Step 4: Delete the `#rail-catalog` section**

Delete:
```html
    <section class="rail" id="rail-catalog" data-rail-accent="catalog" aria-labelledby="h-catalog">
      <h2 id="h-catalog">Software Catalog <span class="rail-hint">curated install/remove — 20 vetted programs, no arbitrary images</span></h2>
      <div id="catalog-grid"></div>
    </section>

```
(the trailing blank line before `<section class="rail" id="rail-reference"...` too, to avoid a double-blank-line artifact).

- [ ] **Step 5: Remove the `catalog.js` script tag if one exists in `index.html`**

Run:
```bash
grep -n 'catalog.js' /home/bear/Claude/media-stack/control-panel/static/index.html
```
`catalog.js` is loaded as an ES module import from `app.js` (see Task 5), not a direct `<script>` tag in `index.html` — expected output is no output. If a direct script tag is found, delete that line too.

- [ ] **Step 6: Verify final rail order**

Run:
```bash
grep -n 'id="rail-' /home/bear/Claude/media-stack/control-panel/static/index.html
```
Expected output, in this exact order:
```
id="rail-poster-sync"
id="rail-plex-health"
id="rail-overview"
id="rail-fleet"
id="rail-host"
id="rail-reference"
```

- [ ] **Step 7: Commit**

```bash
cd /home/bear/Claude/media-stack
git add control-panel/static/index.html
git commit -m "feat: promote poster sync to top rail, remove software catalog rail"
```

---

## Task 4: `poster-sync.js` — drop modal wrapper

**Files:**
- Modify: `control-panel/static/js/poster-sync.js:398-404`

**Interfaces:**
- Consumes: `#poster-sync-form` and related IDs from Task 3's HTML (unchanged element IDs, so `buildPosterSync()`'s internals need zero changes).
- Produces: `export function buildPosterSync()` — was already exported (line 267), now the sole exported entry point since `buildPosterDock` is deleted. Task 5 (`app.js`) imports `buildPosterSync` directly.

- [ ] **Step 1: Delete `buildPosterDock`**

Delete lines 398-404:
```js
export function buildPosterDock() {
  document.getElementById("poster-dock-close").addEventListener("click", () => {
    document.getElementById("poster-dock").hidden = true;
    closePosterStream();
  });
  buildPosterSync();
}
```
`buildPosterSync` (defined above it, line 267) is already `export`ed and needs no changes — the file now ends after `buildPosterSync`'s closing brace (line 396).

- [ ] **Step 2: Verify no other reference to `buildPosterDock` or `poster-dock-close` remains**

```bash
grep -rn 'buildPosterDock\|poster-dock-close' /home/bear/Claude/media-stack/control-panel/static/
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd /home/bear/Claude/media-stack
git add control-panel/static/js/poster-sync.js
git commit -m "refactor: drop poster-sync modal wrapper, rail is always visible now"
```

---

## Task 5: `app.js` and `host.js` — wiring cleanup

**Files:**
- Modify: `control-panel/static/app.js:19-20,40-41`
- Modify: `control-panel/static/js/host.js:90-102`

**Interfaces:**
- Consumes: `buildPosterSync` export from Task 4's `poster-sync.js`.
- Produces: nothing new — this task only removes dead wiring (catalog import/call, poster-dock open button, stale `buildPosterDock` import).

- [ ] **Step 1: Update `app.js` imports**

In `control-panel/static/app.js`, replace line 19:
```js
import { buildPosterDock } from "./js/poster-sync.js";
```
with:
```js
import { buildPosterSync } from "./js/poster-sync.js";
```
Delete line 20 entirely:
```js
import { buildCatalog } from "./js/catalog.js";
```

- [ ] **Step 2: Update `bootApp()` calls**

In `control-panel/static/app.js`, replace:
```js
  buildPosterDock();
  buildCatalog();
```
with:
```js
  buildPosterSync();
```

- [ ] **Step 3: Remove the "Poster sync — Open" row from `host.js`**

In `control-panel/static/js/host.js`, delete lines 90-102:
```js
  const posterRow = document.createElement("div");
  posterRow.className = "rule-row";
  posterRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">Poster sync</span>
      <span class="rule-desc">Replace posters with the top-voted TMDb match, one library at a time.</span>
    </div>
    <div class="rule-actions"><button class="btn-ghost" type="button">Open</button></div>
  `;
  wrap.appendChild(posterRow);
  posterRow.querySelector("button").addEventListener("click", () => {
    document.getElementById("poster-dock").hidden = false;
  });

```
This row lived in the Host rail's "Fleet-wide actions" lane — it's redundant now that Poster Sync is always visible at the top of the page. Read the surrounding function first (`buildHostActions` in `host.js`) to confirm the exact boundaries before deleting, since adjacent rows (e.g. "Prune unused Docker space") must remain untouched.

- [ ] **Step 4: Verify no dangling references**

```bash
grep -rn 'buildPosterDock\|buildCatalog\|poster-dock' /home/bear/Claude/media-stack/control-panel/static/
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
cd /home/bear/Claude/media-stack
git add control-panel/static/app.js control-panel/static/js/host.js
git commit -m "refactor: wire poster sync directly, drop catalog boot call and redundant open-poster-dock action"
```

---

## Task 6: Delete `catalog.js`, update theme handling in `settings.js`

**Files:**
- Delete: `control-panel/static/js/catalog.js`
- Modify: `control-panel/static/js/settings.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `applyTheme(theme)` now accepts `"amber"`/`"green"` and sets `#theme-switch`'s checked state and `.switch-label` text accordingly — no other module calls `applyTheme` or reads `theme-switch`, so this is a self-contained change.

- [ ] **Step 1: Delete `catalog.js`**

```bash
rm /home/bear/Claude/media-stack/control-panel/static/js/catalog.js
```

- [ ] **Step 2: Update `applyTheme` in `settings.js`**

In `control-panel/static/js/settings.js`, replace lines 14-18:
```js
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const input = document.getElementById("theme-switch");
  if (input) input.checked = theme === "dark";
}
```
with:
```js
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const input = document.getElementById("theme-switch");
  if (input) input.checked = theme === "green";
  const label = document.querySelector(".switch-label");
  if (label) label.textContent = theme === "green" ? "Green" : "Amber";
}
```
(Checked = green, unchecked = amber — matches the existing pattern where checked meant the "second" value. The `.switch-label` text is now updated dynamically since it must show whichever theme is active, unlike before where "Dark"/"Light" happened to work as a static label that didn't need updating — actually check: previously the label always said "Dark" regardless of state. Re-verify this against the live-rendered checkbox behavior in Task 7's manual test — if the prior static "Dark" label was intentional (e.g., label describes the checked/right-hand state, not current state), keep this dynamic update anyway since "Amber"/"Green" ambiguity would be a readability regression the old dark/light label didn't have.)

- [ ] **Step 3: Update the default settings fallback**

In `control-panel/static/js/settings.js`, replace line 27:
```js
  let settings = { theme: "dark" };
```
with:
```js
  let settings = { theme: "amber" };
```

- [ ] **Step 4: Update the change handler's theme mapping**

Replace lines 34-38:
```js
  document.getElementById("theme-switch").addEventListener("change", async (e) => {
    const theme = e.target.checked ? "dark" : "light";
    applyTheme(theme);
    await patchSettings({ theme });
  });
```
with:
```js
  document.getElementById("theme-switch").addEventListener("change", async (e) => {
    const theme = e.target.checked ? "green" : "amber";
    applyTheme(theme);
    await patchSettings({ theme });
  });
```

- [ ] **Step 5: Update the file's header comment**

Replace line 1-3:
```js
/* Persisted-settings wiring: theme (server-side, /api/settings) and the
   log console drawer (client-only UI state, localStorage - no server
   round-trip needed for something this ephemeral). */
```
with:
```js
/* Persisted-settings wiring: theme (amber/green Pip-Boy palette,
   server-side via /api/settings) and the log console drawer (client-only
   UI state, localStorage - no server round-trip needed for something
   this ephemeral). */
```

- [ ] **Step 6: Verify no remaining `"dark"`/`"light"` string literals in JS**

```bash
grep -rn '"dark"\|'"'"'dark'"'"'\|"light"\|'"'"'light'"'"'' /home/bear/Claude/media-stack/control-panel/static/js/ /home/bear/Claude/media-stack/control-panel/static/app.js
```
Expected: no output.

- [ ] **Step 7: Run the JS test suite**

```bash
cd /home/bear/Claude/media-stack/control-panel/static/js && node --test *.test.js
```
Expected: `tests 8`, `pass 8`, `fail 0` (same baseline as before this plan — no new logic was added that needs new tests, and nothing in `catalog.js` or the removed modal wiring had test coverage to lose).

- [ ] **Step 8: Commit**

```bash
cd /home/bear/Claude/media-stack
git add -A control-panel/static/js/
git commit -m "feat: wire amber/green theme switch, delete software catalog module"
```

---

## Task 7: Manual verification in browser

**Files:** none (verification only)

**Interfaces:** none

- [ ] **Step 1: Rebuild and restart the control-panel container**

```bash
cd /home/bear/Claude/media-stack
docker compose up -d --build control-panel
```
(`--build` is required, not just `restart` — static JS/CSS changes need a rebuild per this repo's standing control-panel verification rule; a plain container restart serves stale cached files.)

- [ ] **Step 2: Hard-reload the control panel in browser**

Navigate to the control panel's URL and hard-reload with `Ctrl+Shift+R` (a normal reload can still serve cached JS/CSS).

- [ ] **Step 3: Verify theme toggle**

Click the theme switch. Confirm:
- Page recolors between amber (`#ffb000` on near-black) and green (`#33ff33` on near-black).
- Switch label reads "Amber" / "Green" correctly for each state.
- Hard-reload again — theme choice persists (confirms `/api/settings` round-trip works).

- [ ] **Step 4: Verify Poster Sync is the first rail**

Confirm the page's first visible rail (top of `#col-main`, before Plex Health) is "Poster Sync", rendered inline (not a modal/overlay), with the library dropdown populated (or a "No movie/show libraries found" message if Plex has none configured — either is correct, just confirm it's not stuck on "Loading libraries…").

- [ ] **Step 5: Verify Poster Sync functions**

Pick a library, try each mode (Auto, Review, Gallery) and confirm each renders its expected UI inline (log lines for Auto, candidate cards for Review, image grid for Gallery) exactly as it did in the old modal — this is a relocation, not a behavior change, so parity is the bar.

- [ ] **Step 6: Verify Software Catalog is gone**

Confirm no "Software Catalog" rail appears anywhere on the page. Open the browser console and confirm no errors referencing `catalog-grid`, `buildCatalog`, or `catalog.js` (a 404 on a deleted script or a null-element error would indicate a missed reference).

- [ ] **Step 7: Verify remaining rail order and Host rail**

Confirm top-to-bottom order is: Poster Sync, Plex Health, Overview, Fleet, Host, Reference. In the Host rail's "Fleet-wide actions" lane, confirm there's no "Poster sync — Open" row (it was removed in Task 5 since poster sync is always visible now).

- [ ] **Step 8: No commit for this task** — it's verification-only. If any step fails, fix the underlying issue in its owning task and re-run this task's steps from Step 1.

---

## Self-Review Notes

- **Spec coverage:** all 4 numbered design sections (theme system, poster sync promotion, rail reorder, catalog removal) map to Tasks 1-6; the spec's "Files touched" list is fully covered including the command-palette manifest line — confirmed during research that no palette command opens the poster dock (only `host.js`'s "Open" button did), so that spec line was based on an incorrect assumption and is corrected in Task 5 instead of chased as a phantom file.
- **Placeholder scan:** no TBD/TODO; every step has literal before/after code.
- **Type consistency:** `theme` string values (`"amber"`/`"green"`) are consistent across Task 1 (Python defaults), Task 2 (CSS selectors), and Task 6 (JS). Element IDs in Task 3's HTML match exactly what Task 4's `poster-sync.js` already queries (verified against the live file, zero ID changes).
- **Scope check:** single cohesive UI redesign, appropriately one plan — no sub-project decomposition needed.
