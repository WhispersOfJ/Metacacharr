# Pip-Boy Control Panel Redesign

Date: 2026-08-20
Status: Approved, ready for implementation plan

## Problem

The control panel is a long, undifferentiated scroll of rails with no visual
identity. Two structural issues compound this:

1. **Poster Sync is buried.** It's a hidden modal (`#poster-dock`, `hidden`
   by default) only reachable through the command palette, despite being one
   of the panel's most-used features.
2. **Software Catalog is dead weight in this UI.** The 20-program
   install/remove grid (`#rail-catalog`, `catalog.js`) no longer earns its
   place at the top of the scroll.

## Goals

- Give the panel a strong visual identity: a Fallout Pip-Boy CRT terminal
  theme, with amber and green palette variants.
- Promote Poster Sync from hidden modal to the first, always-visible rail.
- Remove Software Catalog from the UI entirely.
- Reorder remaining rails so the most actionable/live information leads.

## Non-Goals

- Removing the Software Catalog backend (API routes, docker-compose control
  logic). This pass is frontend-only; backend removal is a separate,
  explicitly-scoped follow-up.
- New poster-sync functionality. The gallery, quality scan, and before/after
  review already exist in `poster-sync.js` — this pass relocates and
  restyles, it does not extend behavior.
- A third light/dark (non-Pip-Boy) mode. The existing light/dark toggle is
  replaced outright by amber/green, not supplemented.

## Design

### 1. Theme system

Replace the `theme` setting's two values (`"dark"` / `"light"`) with two new
values (`"amber"` / `"green"`), both Pip-Boy CRT palettes. The existing
`:root[data-theme]` token-swap architecture in `style.css` already supports
this pattern (see `style.css:14-101`) — only the token *values* change, not
the mechanism.

**Palette tokens:**
- **Amber** — foreground `#ffb000` on near-black `#0a0805`, amber glow
  (`text-shadow`/`box-shadow`) on headers and live values.
- **Green** — foreground `#33ff33` on near-black `#050a05`, green glow on
  the same elements.

**Shared CRT effects** (theme-independent, added once to base rules, not
duplicated per palette):
- Scanline overlay: fixed-position pseudo-element with a repeating linear
  gradient, low opacity, `pointer-events: none`.
- Subtle vignette darkening toward the viewport edges.
- Text-shadow glow on `h2`, `.vital-value`, and other live-data elements.
- Monospace terminal font stack (system/`ui-monospace` fallback chain — no
  external font fetch, consistent with this repo's no-CDN/self-contained
  habit).
- Beveled, chunky panel borders replacing the current rounded-card look on
  `.rail`.

**Settings wiring** (`settings.js`):
- `applyTheme` sets `document.documentElement.dataset.theme` to `amber` or
  `green` (unchanged mechanism, new value set).
- The theme-switch checkbox becomes an amber/green toggle; update its label
  and the `change` handler's `theme` value mapping.
- `index.html`'s `#theme-switch` markup gets updated label text describing
  the amber/green choice instead of light/dark.

**Backend default** (`control-panel/core/settings.py:14` and
`control-panel/settings_store.py:17`): change `"theme": "dark"` to
`"theme": "amber"` in both `DEFAULTS` dicts. No schema/enum validation
exists in either module (`update_settings` only filters by key presence),
so no migration logic is needed — this is a default-value change only.
`core/settings.py` is the live DB-backed module per its own docstring
("DB-backed replacement for settings_store.py"); `settings_store.py` appears
superseded but is updated too for consistency in case it's still referenced
anywhere.

### 2. Poster Sync promotion

Move the `#poster-dock` markup (`index.html:241-284`) out of its current
position (a bottom-of-body hidden overlay, structurally separate from
`#workspace`) into a new rail inside `#col-main`:

```html
<section class="rail" id="rail-poster-sync" data-rail-accent="poster-sync" aria-labelledby="h-poster-sync">
  <h2 id="h-poster-sync">Poster Sync</h2>
  <!-- existing poster-sync-form, poster-log, poster-review-grid, poster-gallery markup, unchanged -->
</section>
```

This becomes the **first** rail in `#col-main`, immediately inside
`<div id="workspace">`, before `#rail-plex-health`.

- Remove the `hidden` attribute — it renders permanently, not on-demand.
- `poster-sync.js` keeps its existing fetch/render logic untouched; only the
  modal open/close wiring (show/hide calls, backdrop click-to-close, the
  `#poster-dock-close` handler) is removed since there's no longer a modal
  state to toggle.
- The command-palette entry that used to open the poster-sync dock is
  removed from the palette manifest — the feature is always visible, so a
  "jump to it" palette command is redundant. (If a quick "scroll to Poster
  Sync" affordance is wanted later, that's a separate small addition, not
  part of this pass.)

Per the earlier decision, **all** poster-sync UI (form, log, review grid,
gallery, quality scan) moves inline — no residual modal for any part of it.

### 3. Rail reorder

New top-to-bottom order in `#col-main`:

1. Poster Sync (new)
2. Plex Health (`#rail-plex-health`)
3. Overview (`#rail-overview`)
4. Fleet (`#rail-fleet`)
5. Host (`#rail-host`)
6. Reference (`#rail-reference`)

`#rail-catalog` is deleted (see below), not reordered.

This is a pure DOM-order change in `index.html`; no JS logic depends on rail
position (each section is queried by ID, not by sibling order).

### 4. Software Catalog removal

- Delete `#rail-catalog` block from `index.html` (currently lines
  158-161).
- Delete `control-panel/static/js/catalog.js`.
- Remove `catalog.js`'s `<script>` include from `index.html`.
- Remove any import/init call wiring it into `app.js` or `core.js`.
- Grep the JS test suite (`core.test.js`, `fleet.test.js`) for catalog
  references before deleting — if catalog has dedicated tests, remove them
  too; if it's only referenced incidentally, leave the rest of the suite
  intact.

Backend catalog API routes and docker-compose control endpoints are **not**
touched in this pass (see Non-Goals).

## Files touched

- `control-panel/static/index.html` — rail reorder, poster-dock relocation,
  catalog rail removal, theme-switch label update, script include removal
- `control-panel/static/style.css` — Pip-Boy palette tokens (amber/green),
  CRT effect base rules, panel border/font updates
- `control-panel/static/js/settings.js` — theme value mapping
  (dark/light → amber/green)
- `control-panel/static/js/poster-sync.js` — remove modal show/hide wiring
- `control-panel/static/js/catalog.js` — deleted
- `control-panel/static/js/app.js` — remove catalog import/init if present
- `control-panel/core/settings.py` — default theme value
- `control-panel/settings_store.py` — default theme value (consistency)
- Command palette manifest (wherever poster-sync-dock-open command is
  defined) — remove the now-redundant "open poster sync" command

## Testing

- Existing suite (`core.test.js`, `fleet.test.js`, `sparkline.test.js`) must
  continue passing — no poster-sync or settings logic changes, only DOM
  relocation and CSS, so no new test surface is expected. Update/remove any
  catalog-specific tests found during the grep above.
- Manual in-browser verification (per this repo's UI-change standard):
  - Theme toggle switches amber ↔ green and persists across a hard reload
    (`Ctrl+Shift+R`) and container restart, per the standing control-panel
    verification rule.
  - Poster Sync renders inline at the top of the page and all its existing
    functions (sync form, log streaming, review grid, gallery, quality
    scan) work identically to their prior modal behavior.
  - Software Catalog rail is gone from the DOM; no console errors from
    missing `catalog-grid` element or dangling event listeners.
  - Remaining rails render in the new order and are otherwise functionally
    unchanged.
