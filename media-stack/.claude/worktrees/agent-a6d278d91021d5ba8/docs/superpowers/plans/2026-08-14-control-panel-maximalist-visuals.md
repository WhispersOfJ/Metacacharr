# Control Panel: Maximalist Visual Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the control panel from restrained "spec-sheet" to a maximalist look (decorative shell + dense data viz) without changing markup IDs, API shapes, or the palette/execution model.

**Architecture:** Extend the existing CSS custom-property system in `control-panel/static/style.css` with per-rail accent hues and a texture layer; extract the two duplicated sparkline renderers (`host.js`, `plex-health.js`) into one shared `sparkline.js` module and add a third consumer in `fleet.js` for per-group CPU/mem trend. No new JS dependencies, no build step, no backend changes except one small `/api/containers` history field.

**Tech Stack:** Vanilla ES modules, plain CSS custom properties, inline SVG (no chart library), FastAPI (Python) backend.

**Spec:** `docs/superpowers/specs/2026-08-14-control-panel-maximalist-redesign-design.md`

## Global Constraints

- No new CSS/JS build tooling — plain files served as-is (spec: Non-goals).
- Max two font families total; already at two (`--font-ui`, `--font-mono`) — do not add a third (spec: Part 1, Typographic contrast).
- Every new CSS custom property needs both a light and dark value (spec: Part 1, Shell changes).
- No new charting library — sparklines stay hand-rolled inline SVG (spec: Part 1, Density changes).
- Existing markup IDs/classes that other JS modules query (`#host-resources`, `.fleet-group`, `.sparkline-block`, etc.) must not be renamed — this is a re-skin, not a markup rewrite (style.css:1-12 header comment already establishes this convention; keep it).
- Manual visual regression checks at 320/768/1024/1440 in both themes before considering a task done (spec: Part 1, Testing).

---

### Task 1: Extract shared sparkline renderer

Two near-duplicate sparkline implementations exist today: `host.js`'s `sparklinePath()`/`renderSparkline()` (viewBox `0 0 100 34`, draws into pre-built `<path class="sparkline-fill">`/`<path class="sparkline-line">` elements) and `plex-health.js`'s `renderSparkline()` (viewBox `0 0 200 40`, writes a single `<polyline>` via `innerHTML`). Task 2 adds a third consumer (Fleet). Unify into one module before adding a third copy.

**Files:**
- Create: `control-panel/static/js/sparkline.js`
- Modify: `control-panel/static/js/host.js` (replace inline `sparklinePath`/`renderSparkline` at lines 189-203 with import)
- Modify: `control-panel/static/js/plex-health.js` (replace inline `renderSparkline` at lines 32-45 with import)
- Test: `control-panel/static/js/sparkline.test.js` (new — plain Node test file, no framework currently in this repo's frontend; see Step 1)

**Interfaces:**
- Produces: `renderSparkline(svgEl, samples, { min = 0, max = 100 } = {})` — writes a `<polyline>` into `svgEl` scaled to a `100 x 34` viewBox coordinate space, clamping each sample to `[min, max]`. Matches `plex-health.js`'s existing call signature (`renderSparkline(el, values, { min, max })`) since that's the richer of the two APIs (supports non-0-100 ranges, which Task 2's Fleet mem values need).
- Produces: `pushHistory(buffer, value, maxLen)` — small helper: `buffer.push(value); if (buffer.length > maxLen) buffer.shift(); return buffer;`. Replaces the repeated push/shift-if-too-long pattern in `host.js:234-237` and `plex-health.js` history handling, and will be reused by Task 2.

- [ ] **Step 1: Write the failing test**

This repo has no existing JS test runner. Use Node's built-in `node:test` (zero dependencies, matches the "no new build tooling" constraint).

```js
// control-panel/static/js/sparkline.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { pushHistory } from "./sparkline.js";

test("pushHistory appends and caps buffer length", () => {
  const buf = [1, 2, 3];
  pushHistory(buf, 4, 3);
  assert.deepEqual(buf, [2, 3, 4]);
});

test("pushHistory does not trim under the cap", () => {
  const buf = [1, 2];
  pushHistory(buf, 3, 5);
  assert.deepEqual(buf, [1, 2, 3]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test control-panel/static/js/sparkline.test.js`
Expected: FAIL — `sparkline.js` does not exist yet (module not found).

- [ ] **Step 3: Write the shared module**

```js
// control-panel/static/js/sparkline.js
/* Shared inline-SVG sparkline renderer. Single implementation used by
   Host, Plex Health, and Fleet — do not fork a per-rail copy; add
   options here instead (see the `min`/`max` clamp, added for Plex
   Health's non-0-100 busy-DB-error counts). */

export function pushHistory(buffer, value, maxLen) {
  buffer.push(value);
  if (buffer.length > maxLen) buffer.shift();
  return buffer;
}

export function renderSparkline(svgEl, samples, { min = 0, max = 100 } = {}) {
  if (!svgEl) return;
  if (!samples.length) {
    svgEl.innerHTML = "";
    return;
  }
  const w = 200, h = 40;
  const range = Math.max(max - min, 1);
  const points = samples.map((v, i) => {
    const x = samples.length === 1 ? w : (i / (samples.length - 1)) * w;
    const y = h - ((Math.min(Math.max(v, min), max) - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  svgEl.innerHTML = `<polyline points="${points}" fill="none" stroke="var(--accent)" stroke-width="1.5" />`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test control-panel/static/js/sparkline.test.js`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire `plex-health.js` to the shared module**

In `control-panel/static/js/plex-health.js`, delete the local `renderSparkline` function (lines 32-45) and add the import at the top:

```js
import { renderSparkline } from "./sparkline.js";
```

The existing call sites (`renderSparkline(document.getElementById("spark-progress"), plexProgressHistory, { min: 0, max: 100 })` etc.) are unchanged since the signature matches exactly.

- [ ] **Step 6: Wire `host.js` to the shared module**

In `control-panel/static/js/host.js`, the existing `renderSparkline` (lines 199-203) targets pre-built `<path class="sparkline-fill">`/`<path class="sparkline-line">` elements with a `viewBox 0 0 100 34`. The shared module instead writes a `<polyline>` into a plain `<svg>`. Update the markup this function builds (in `buildHostResources()`, lines 208-220) to drop the two `<path>` children and match Plex Health's plain `<svg viewBox="0 0 200 40">` shape, then delete the local `sparklinePath`/`renderSparkline` (lines 189-203) and import the shared one:

```js
import { renderSparkline, pushHistory } from "./sparkline.js";
```

```js
// buildHostResources(), replace the two <svg>...</svg> blocks with:
<svg class="sparkline" viewBox="0 0 200 40" preserveAspectRatio="none"></svg>
```

Update `refreshHostResources()` (lines 223-246) to use `pushHistory` instead of the manual push/shift:

```js
pushHistory(cpuHistory, data.cpu_percent, RESOURCE_HISTORY_LEN);
pushHistory(memHistory, data.mem_percent, RESOURCE_HISTORY_LEN);
```

- [ ] **Step 7: Manual smoke test**

Start the control panel (see restart instructions at the end of this plan) and open it in a browser. Confirm:
- Plex Health rail's two sparklines (`#spark-progress`, `#spark-busydb`) still render on data updates.
- Host rail's CPU/RAM sparklines still render on the 5s poll.

- [ ] **Step 8: Commit**

```bash
git add control-panel/static/js/sparkline.js control-panel/static/js/sparkline.test.js control-panel/static/js/host.js control-panel/static/js/plex-health.js
git commit -m "refactor: extract shared sparkline renderer from host.js and plex-health.js"
```

---

### Task 2: Add per-group CPU/mem sparkline history to Fleet rail

**Files:**
- Modify: `control-panel/static/js/fleet.js` (add sparkline rendering inside the per-group loop, `refreshFleet()` lines 135-190)
- Modify: `control-panel/static/index.html` (no ID changes needed — Fleet already renders into `#fleet-groups`, dynamically generated per-group markup)
- Modify: `control-panel/app.py` or wherever `/api/containers` is implemented — add `cpu_percent`/`mem_percent` per container if not already present
- Test: `control-panel/static/js/fleet.test.js` (new)

**Interfaces:**
- Consumes: `renderSparkline`, `pushHistory` from `./sparkline.js` (Task 1).
- Consumes: `/api/containers` response — confirm/extend each item to include `cpu_percent: number, mem_percent: number` (Docker stats API already exposes these per-container; if the endpoint doesn't currently return them, add via `container.stats(stream=False)` in the backend handler).
- Produces: per-group history buffers keyed by container name, `Map<string, {cpu: number[], mem: number[]}>`, module-scoped in `fleet.js` (mirrors the existing `collapsedGroups` module-scoped Set pattern already in that file).

- [ ] **Step 1: Check whether `/api/containers` already returns CPU/mem stats**

```bash
grep -n "cpu_percent\|mem_percent\|containers.stats\|/api/containers" control-panel/app.py control-panel/main.py control-panel/core/*.py control-panel/services/**/*.py 2>/dev/null
```

If `cpu_percent`/`mem_percent` are already present in the response, skip Step 2 and go to Step 3. If not, proceed to Step 2.

- [ ] **Step 2: Add per-container stats to the backend response (only if Step 1 found none)**

Locate the handler backing `/api/containers` (found via the grep in Step 1). Docker's Python SDK exposes non-streaming stats via `container.stats(stream=False)`. Add a helper next to the existing container-listing code:

```python
def _container_cpu_mem_percent(container) -> tuple[float, float]:
    """Instantaneous CPU% and mem% for one container, Docker-stats-API shaped.
    stream=False blocks briefly (~1s) per call — acceptable at Fleet's
    existing 15s poll cadence, not called per-frame."""
    stats = container.stats(stream=False)
    cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
    sys_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
    online_cpus = stats["cpu_stats"].get("online_cpus") or len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage") or [1])
    cpu_percent = (cpu_delta / sys_delta * online_cpus * 100.0) if sys_delta > 0 else 0.0
    mem_usage = stats["memory_stats"].get("usage", 0)
    mem_limit = stats["memory_stats"].get("limit", 1)
    mem_percent = (mem_usage / mem_limit * 100.0) if mem_limit else 0.0
    return round(cpu_percent, 1), round(mem_percent, 1)
```

Call this inside the existing per-container loop that builds the `/api/containers` response, adding the two fields to each item's dict. Guard with try/except returning `0.0, 0.0` on failure (a stopped container has no stats) — do not let one container's stats call break the whole endpoint.

- [ ] **Step 3: Write the failing frontend test**

```js
// control-panel/static/js/fleet.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { groupHistoryFor } from "./fleet.js";

test("groupHistoryFor returns the same buffer object across calls for the same name", () => {
  const a = groupHistoryFor("radarr");
  const b = groupHistoryFor("radarr");
  assert.equal(a, b);
});

test("groupHistoryFor returns distinct buffers for distinct names", () => {
  const a = groupHistoryFor("radarr");
  const b = groupHistoryFor("sonarr");
  assert.notEqual(a, b);
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `node --test control-panel/static/js/fleet.test.js`
Expected: FAIL — `groupHistoryFor` is not exported from `fleet.js`.

- [ ] **Step 5: Implement `groupHistoryFor` and wire sparklines into the Fleet render loop**

Add near the top of `fleet.js`, alongside the existing `collapsedGroups` module state:

```js
import { renderSparkline, pushHistory } from "./sparkline.js";

const FLEET_HISTORY_LEN = 24; // matches Host's RESOURCE_HISTORY_LEN
const containerHistory = new Map(); // name -> { cpu: number[], mem: number[] }

export function groupHistoryFor(name) {
  if (!containerHistory.has(name)) {
    containerHistory.set(name, { cpu: [], mem: [] });
  }
  return containerHistory.get(name);
}
```

In `refreshFleet()`, after computing `hits` (line 153) and before the render loop, push new samples for every container present in this poll:

```js
for (const c of data) {
  const hist = groupHistoryFor(c.name);
  pushHistory(hist.cpu, c.cpu_percent ?? 0, FLEET_HISTORY_LEN);
  pushHistory(hist.mem, c.mem_percent ?? 0, FLEET_HISTORY_LEN);
}
```

Add a small sparkline block to each group's header markup (inside the `groupEl.innerHTML` template around line 168-174) — one sparkline per group showing the group's *max* CPU% across its containers per poll (keeps this a per-group summary, not per-container, matching the spec's "Fleet gains sparkline history" framing rather than one sparkline per container which would be unreadable at 209-function density):

```js
const groupCpuHistory = groupHistoryFor(`__group__${group}`);
pushHistory(groupCpuHistory.cpu, Math.max(0, ...items.map((c) => c.cpu_percent ?? 0)), FLEET_HISTORY_LEN);
```

```js
groupEl.innerHTML = `
  <div class="fleet-group-head" data-group="${escapeHtml(group)}">
    <span class="chev">▾</span>${escapeHtml(group)}
    <span class="fleet-group-count">${items.length} container${items.length === 1 ? "" : "s"}${downCount ? ` · ${downCount} need attention` : ""}</span>
    <svg class="sparkline fleet-group-spark" viewBox="0 0 200 40" preserveAspectRatio="none"></svg>
  </div>
  <div class="rule-list">${items.map(fleetRowHtml).join("")}</div>
`;
```

Right after `wrap.appendChild(groupEl)` (line 175), render the group's sparkline:

```js
renderSparkline(groupEl.querySelector(".fleet-group-spark"), groupCpuHistory.cpu, { min: 0, max: 100 });
```

- [ ] **Step 6: Run test to verify it passes**

Run: `node --test control-panel/static/js/fleet.test.js`
Expected: PASS (2 tests)

- [ ] **Step 7: Add CSS for the new sparkline placement**

In `control-panel/static/style.css`, near the existing `.fleet-group-head` rule, add:

```css
.fleet-group-head { position: relative; }
.fleet-group-spark { width: 64px; height: 18px; margin-left: auto; opacity: 0.85; }
```

(Exact selector/flex context depends on `.fleet-group-head`'s current CSS — confirm its `display` value before adding `margin-left: auto`; if it's not already `display: flex`, add `display: flex; align-items: center; gap: 8px;` to `.fleet-group-head` so the sparkline sits inline with the count text.)

- [ ] **Step 8: Manual smoke test**

Restart the control panel, open it, expand a Fleet group, confirm a small sparkline renders in the group header and updates on the ~15s poll.

- [ ] **Step 9: Commit**

```bash
git add control-panel/static/js/fleet.js control-panel/static/js/fleet.test.js control-panel/static/style.css control-panel/app.py
git commit -m "feat: add per-group CPU sparkline history to Fleet rail"
```

---

### Task 3: Per-rail accent hues (decorative shell, part 1)

**Files:**
- Modify: `control-panel/static/style.css` (add new custom properties near the existing `:root` block, lines 14-100; add per-rail class rules)
- Modify: `control-panel/static/index.html` (add a data attribute per rail `<section>` to key the accent)

**Interfaces:**
- Produces: CSS custom properties `--rail-plex-health`, `--rail-overview`, `--rail-fleet`, `--rail-host`, `--rail-catalog`, `--rail-reference` (light + dark values), consumed by a new `.rail[data-rail-accent]` selector.

- [ ] **Step 1: Add per-rail accent tokens**

In `control-panel/static/style.css`, inside `:root` (after line 37, following `--unknown`) add six new hues distinct from `--accent` (violet) so each rail reads as its own zone at a glance — picked to stay legible against both light (`#f3f1f6`) and dark (`#131018`) backgrounds:

```css
  --rail-plex-health: #b3403b;   /* red-orange: health/alerts */
  --rail-overview: #6a4fd0;      /* violet: matches existing --accent, this is the "home" rail */
  --rail-fleet: #1f8f6e;         /* green: running state */
  --rail-host: #1c7ea9;          /* blue: infra */
  --rail-catalog: #a9701c;       /* amber: install/acquire */
  --rail-reference: #837e99;     /* muted: passive/reference */
```

Add the same six inside `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }` (after line 72) and inside `:root[data-theme="dark"]` (after line 86), using brighter variants matching how `--accent` brightens from `#6a4fd0` to `#a996ff` between light/dark today:

```css
  --rail-plex-health: #ef5b6a;
  --rail-overview: #a996ff;
  --rail-fleet: #4fd1ac;
  --rail-host: #4fb8e8;
  --rail-catalog: #e2a23c;
  --rail-reference: #837c9c;
```

And inside `:root[data-theme="light"]` (after line 99), the light values repeated (same as the base `:root` block, matching the existing pattern where light values are duplicated in both places).

- [ ] **Step 2: Key each rail to its accent in the markup**

In `control-panel/static/index.html`, add `data-rail-accent="<name>"` to each of the six `<section class="rail" ...>` elements:

```html
<section class="rail" id="rail-plex-health" data-rail-accent="plex-health" ...>
<section class="rail" id="rail-overview" data-rail-accent="overview" ...>
<section class="rail" id="rail-fleet" data-rail-accent="fleet" ...>
<section class="rail two-lane" id="rail-host" data-rail-accent="host" ...>
<section class="rail" id="rail-catalog" data-rail-accent="catalog" ...>
<section class="rail" id="rail-reference" data-rail-accent="reference" ...>
```

- [ ] **Step 3: Add the CSS rule consuming the attribute**

In `style.css`, near the `.glass-card` rules (after line 135 or thereabouts — find the closing of the current `.glass-card` block first), add:

```css
.rail[data-rail-accent] { border-top: 3px solid var(--rail-accent, var(--accent)); }
.rail[data-rail-accent="plex-health"] { --rail-accent: var(--rail-plex-health); }
.rail[data-rail-accent="overview"] { --rail-accent: var(--rail-overview); }
.rail[data-rail-accent="fleet"] { --rail-accent: var(--rail-fleet); }
.rail[data-rail-accent="host"] { --rail-accent: var(--rail-host); }
.rail[data-rail-accent="catalog"] { --rail-accent: var(--rail-catalog); }
.rail[data-rail-accent="reference"] { --rail-accent: var(--rail-reference); }
.rail[data-rail-accent] h2 { color: var(--rail-accent); }
```

(Check whether `.rail` already has a `border-top` or conflicting border rule before adding — if so, adjust the property to whichever edge is free, e.g. `border-left` instead, to avoid clobbering existing styling. Verify by grepping `grep -n "\.rail {" control-panel/static/style.css` and reading that block first.)

- [ ] **Step 4: Manual visual check**

Restart the control panel, open in a browser, confirm each rail's heading and top border now shows a distinct color, in both light and dark theme (toggle via the existing switch).

- [ ] **Step 5: Commit**

```bash
git add control-panel/static/style.css control-panel/static/index.html
git commit -m "feat: give each rail a distinct accent hue"
```

---

### Task 4: Background texture layer (decorative shell, part 2)

**Files:**
- Modify: `control-panel/static/style.css` (extend the `body` background rule at lines 105-117)

**Interfaces:**
- None — pure CSS, no JS/markup dependency.

- [ ] **Step 1: Add a subtle diagonal-hatch texture behind the existing radial glows**

The current `body` background (lines 105-117) already layers two radial gradients. Extend `background-image` with a third layer: a repeating diagonal line pattern via CSS `repeating-linear-gradient`, kept faint enough not to fight text contrast, consistent with the drafting-table/stamp-sheet motif already established by `.stampgrid` in the header.

```css
body {
  background-color: var(--bg);
  background-image:
    radial-gradient(900px 420px at 12% -8%, var(--accent-tint), transparent 60%),
    radial-gradient(700px 360px at 100% 0%, var(--accent-tint), transparent 55%),
    repeating-linear-gradient(135deg, var(--line) 0px, var(--line) 1px, transparent 1px, transparent 28px);
  background-attachment: fixed;
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: 0.906rem;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
}
```

`var(--line)` is already theme-aware (light: `rgba(33,29,43,0.10)`, dark: `rgba(239,234,247,0.12)`) so the hatch stays faint in both themes without new tokens.

- [ ] **Step 2: Manual visual check**

Restart the control panel, confirm a faint diagonal hatch is visible across the page background in both themes, and confirm no text/card legibility regression (cards sit on `.glass-card`'s own `--glass`/`--glass-strong` background which stays opaque enough to read over the hatch — the existing `backdrop-filter: blur(var(--blur))` already handles this since it blurs whatever is behind the card).

- [ ] **Step 3: Commit**

```bash
git add control-panel/static/style.css
git commit -m "feat: add diagonal-hatch texture layer to page background"
```

---

### Task 5: Typographic contrast pass on rail headings

**Files:**
- Modify: `control-panel/static/style.css` (locate and update the `h2`/`.rail h2` rule)

**Interfaces:**
- None — pure CSS.

- [ ] **Step 1: Find the current heading rule**

```bash
grep -n "^h2\|\.rail h2\|rail-sub" control-panel/static/style.css
```

- [ ] **Step 2: Widen the scale contrast**

Using whatever the grep in Step 1 reveals as the current `h2`/`.rail h2` font-size (read the surrounding 5 lines first via Read tool to get exact current values — do not guess), increase `font-size` and `font-weight` for rail headings so they read as bold section dividers against the denser card content below them, and reduce `.rail-sub` (subheadings, e.g. "History", "Live resources") proportionally so the hierarchy gap widens rather than both scaling together. Concretely, if `.rail h2` is currently in the ~1.1-1.3rem range (typical for this design's `html { font-size: 120% }` base), change to:

```css
.rail h2 { font-size: 1.65rem; font-weight: 800; letter-spacing: -0.01em; }
.rail-sub { font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-soft); }
```

(If the existing rule already sets some of these properties with different selectors or specificity, edit in place rather than adding a second conflicting rule — read the actual current CSS block before writing this edit.)

- [ ] **Step 3: Manual visual check**

Restart the control panel, confirm rail headings are now visibly larger/bolder than before and subheadings (e.g. "History", "Live resources", "Fleet-wide actions") are small-caps and muted, creating clearer hierarchy. Check both themes and at least 768px and 1440px widths.

- [ ] **Step 4: Commit**

```bash
git add control-panel/static/style.css
git commit -m "style: widen typographic contrast between rail headings and subheadings"
```

---

### Task 6: Card depth pass — accent-tinted card borders per rail

**Files:**
- Modify: `control-panel/static/style.css` (extend `.glass-card` rule, lines 130-135+, and add rail-scoped card variants)

**Interfaces:**
- Consumes: `--rail-accent` custom property set per-rail by Task 3's `[data-rail-accent]` selectors.

- [ ] **Step 1: Read the full current `.glass-card` rule**

```bash
sed -n '127,160p' control-panel/static/style.css
```

Read the actual box-shadow/border values before editing (do not assume — use what Step 1's output shows).

- [ ] **Step 2: Add a stronger, rail-tinted shadow to cards nested inside an accented rail**

Add after the existing `.glass-card` block:

```css
.rail[data-rail-accent] .glass-card,
.rail[data-rail-accent] .catalog-card {
  box-shadow: 0 1px 2px var(--line), 0 8px 24px -12px var(--rail-accent, var(--accent));
}
```

This layers a colored ambient shadow (using each rail's Task-3 accent) under every card in that rail, on top of whatever hairline shadow `.glass-card` already defines — read Step 1's output to confirm this doesn't duplicate an existing `box-shadow` declaration; if `.glass-card` already sets `box-shadow`, merge into one rule instead of two competing ones.

- [ ] **Step 3: Manual visual check**

Restart, confirm cards within each rail now show a subtle colored glow matching that rail's accent (most visible in dark theme), and confirm no card became illegible or the glow isn't so strong it reads as an error state (compare against `--bad`'s red — Plex Health's rail accent is also reddish, so specifically verify a Plex Health card's glow doesn't look like an error banner).

- [ ] **Step 4: Commit**

```bash
git add control-panel/static/style.css
git commit -m "style: add rail-tinted ambient shadow to cards"
```

---

### Task 7: Full visual regression pass

**Files:**
- None modified — verification-only task.

- [ ] **Step 1: Screenshot at each breakpoint, both themes**

Using the `claude-in-chrome` or `chrome-devtools` MCP tools (load via ToolSearch if deferred), navigate to the running control panel and capture screenshots at 320px, 768px, 1024px, 1440px widths, toggling the theme switch (`#theme-switch`) between each set. 8 screenshots total.

- [ ] **Step 2: Check for regressions**

For each screenshot, confirm:
- No horizontal overflow/scrollbar at any width.
- All six rails show their distinct accent color (Task 3).
- Sparklines render with real data, not empty (Tasks 1-2).
- Text remains legible against the new background texture (Task 4).
- Heading hierarchy is visibly clearer than before (Task 5).

- [ ] **Step 3: Command palette smoke test**

Open the command palette (Ctrl+K), run one read-only command (e.g. a status check), confirm the palette overlay still renders correctly on top of the new background/card styling with no z-index regression.

- [ ] **Step 4: Fix any regressions found, then re-run Steps 1-3**

If issues are found, fix inline in the relevant Task's file and re-screenshot only the affected breakpoint/theme combination.

- [ ] **Step 5: Commit if any fixes were needed**

```bash
git add control-panel/static/style.css control-panel/static/index.html
git commit -m "fix: address visual regressions found in maximalist redesign pass"
```

---

## Restart Instructions

After any task, to see changes live:

```bash
docker compose restart control-panel
```

Static files (`style.css`, `*.js`, `index.html`) are served directly by FastAPI with no build step — a container restart picks them up immediately. Hard-reload the browser tab (Ctrl+Shift+R) to bypass any cached JS/CSS, per this project's standing verification rule.
