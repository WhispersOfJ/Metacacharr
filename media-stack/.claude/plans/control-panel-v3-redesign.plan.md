# Control Panel v3 — Redesign Continuation Notes

**Written:** 2026-08-07, mid-session, ahead of a deliberate context reset. This is the
resume-cold document for the redesign work specifically (not the host-helper problem —
that's `host-privileged-helper.plan.md`, a separate document/separate task by request).

**Source of truth for the visual direction and full rationale:** the published design
treatment artifact — https://claude.ai/code/artifact/664830f4-0c52-47b7-a9aa-cc36d1d4bea5
("Control Panel — Redesign Treatment"). Re-fetch it (WebFetch works on claude.ai/code
artifact URLs) at the start of the next session if the visual language needs
re-grounding — it has the full mockups, the phase roadmap, the 20-program catalog
research, and the risk table this plan builds on.

## Status: 4 of 4 phases shipped

| Phase | Status | Commit | Notes |
|---|---|---|---|
| 01 — Design system (dark-glass) | ✅ Done | `c57cebf` | Full CSS re-skin, zero JS markup changes |
| 02 — Software catalog | ✅ Done | `22d00cb` | 20 programs, Docker SDK not compose-file |
| 03 — Maintenance & backups | ✅ Done | `321a8be` | Disk health, live resources, backup UI |
| 04 — Poster Studio | ✅ Done | (this commit) | Gallery grid, before/after hover, paste-URL override, bulk quality scan |

### Phase 04 implementation notes (2026-08-07)

- **Gallery**: `GET /api/posters/gallery` (paginated, 60/page) + `GET /api/posters/thumb/{rating_key}`
  proxies Plex's poster bytes server-side — PLEX_TOKEN never reaches the browser, unlike
  the TMDb/Fanart candidate URLs (those are already public). New "Gallery" option added
  to the existing mode select in the poster-sync dock, not a new page.
- **Before/after hover**: shared `.poster-compare` CSS pattern (two stacked `<img>`,
  top layer fades out on `:hover`) used both in the gallery (current poster is the
  only layer until a paste-URL preview supplies an "after") and in review-mode
  candidate thumbs (candidate on top, current Plex poster - fetched via the new thumb
  proxy - revealed on hover).
- **Manual override**: paste-URL box per gallery card, reuses `/api/posters/apply`
  directly — no file upload, no new backend, per the plan's own "check before building"
  note.
- **Bulk quality scan**: `POST /api/posters/scan` + `/api/posters/scan/stream` (SSE,
  same job shape as sync/review). Flags in `services/posters/quality.py`:
  `placeholder` (small file + near-uniform grey via Pillow), `low_res` (short side
  <300px), `no_poster` (no `thumb` field at all), `language_mismatch` (item's primary
  audio language vs. TMDb's top-voted poster `iso_639_1` - a heuristic proxy, not a
  literal read of what's applied on Plex, documented as such in the code). Pillow added
  as a new dependency (`requirements.txt`).
- Full suite green (460 tests) before deploy; browser-QA'd live in both themes
  (real Movies library, 14,936 items) - gallery pagination, hover compare, live scan
  flag badges, and error states (already-running 409) all confirmed working. Did not
  click a real Apply during QA against the live Plex library - manual-apply mutation
  path is covered by existing/new unit tests instead, not live production data.

All three shipped phases: full test suite green (438 tests as of `321a8be`), browser-QA'd
live against the real stack in both themes before commit, no known regressions.

## What Phase 04 (Poster Studio) actually needs

From the treatment doc's own scoping (user confirmed via AskUserQuestion,
multiSelect, all four picked): **gallery/grid view, bulk quality scan, manual
override/upload per title, live before/after preview.**

### What already exists (don't rebuild)

`control-panel/services/posters/router.py` — already has, and already works:
- `GET /api/posters/libraries` — movie/show libraries from Plex
- `POST /api/posters/sync` + `GET /api/posters/sync/stream` (SSE) — auto-apply top-voted match
- `POST /api/posters/review` + `GET /api/posters/review/stream` (SSE) — candidate list, doesn't auto-apply
- `POST /api/posters/apply` — set one item's poster to an exact URL

Frontend: `static/js/poster-sync.js` (220 lines) — a floating dock (`.poster-dock`,
already re-themed in Phase 01) that triggers sync/review as background jobs and
streams SSE progress as text lines. **No visual poster rendering anywhere yet** — every
existing interaction is "trigger an action, read a log line," never "look at an image."

### What's genuinely net-new

1. **Gallery/grid view** — a real image grid, not a trigger dock. Needs a new endpoint
   that returns poster thumbnail URLs per library (Plex already serves poster art over
   its own HTTP API — check `core/plex_client.py` for the existing token/URL pattern
   used elsewhere, e.g. `stack-plex-kometa`-adjacent code, before inventing a new one).
   Paginate — a real library can be hundreds of titles.

2. **Bulk quality scan** — a background job (same SSE-stream shape as sync/review
   already use) that walks a library and flags:
   - **Low-res**: poster width/height under a floor. Plex's own metadata usually
     exposes the source image dimensions without needing to download the full image
     (check the `thumb`/`art` metadata fields Plex's API returns — may already include
     width/height, or may need a HEAD/partial-GET to a `Content-Length`-bearing image
     URL as a proxy for "probably low-res" if real dimensions aren't cheap to get).
   - **Placeholder**: Plex's own grey-question-mark art. This has a small, finite set of
     known asset hashes/sizes shipped with Plex itself — perceptual hash match (or even
     exact byte-size match, since placeholder art is a fixed asset) against a known
     placeholder fingerprint is simpler than a general image-similarity approach; don't
     reach for a full perceptual-hash library if a byte-size/exact-hash check is enough.
   - **Language mismatch**: check what the treatment doc's poster caveat referenced —
     Bazarr/Radarr language metadata vs. the poster's own locale tag if Plex exposes one.
   This is real, non-trivial backend work — budget real time for it, don't treat it as
   a one-line addition alongside the gallery.

3. **Manual override/upload per title** — new endpoint, but narrow: mirrors
   `/api/posters/apply`'s existing "exact URL" contract (already takes a URL, already
   applies it) — the new part is a small upload-to-URL step (accept a file, store it
   somewhere Plex-servable, then call the existing apply logic) OR just a paste-URL
   field reusing `/api/posters/apply` directly with zero new backend at all. **Check
   whether "upload a local file" is actually required before building file storage** —
   if a paste-URL box satisfies the ask, that's zero new backend, matching the "search
   before building" / vanilla-by-default project rule.

4. **Live before/after preview** — this is UI work, not backend work. The existing
   `/api/posters/review` SSE stream already emits candidate JSON with image URLs per
   item (confirmed by the existing review-thumb rendering in `poster-sync.js` —
   `.poster-review-thumb img`). The "before/after hover" from the treatment doc's
   mockup is a CSS/markup pattern (two stacked images, one revealed on `:hover`) applied
   to data that's already flowing through the existing review stream — likely the
   smallest of the four sub-features once the gallery view (#1) exists to host it in.

### Suggested build order for Phase 04

Gallery grid first (proves the "render real poster images in the panel" plumbing that
everything else depends on) → before/after preview (reuses existing review-stream data
once images can render) → manual override (small, mostly reuses `/api/posters/apply`)
→ bulk quality scan last (the most backend-heavy, most genuinely new logic, benefits
from the gallery already existing as the place to surface flagged results).

### Design-system carryover

Whatever gets built must land in the dark-glass language from Phase 01 — reuse
`.glass-card`, the existing poster-review-grid/poster-review-thumb classes (already
re-themed in the Phase 01 commit, confirmed in `style.css`), and the badge/pill
conventions from the catalog phase (`.lb-pill`-style status chips) rather than
inventing a fourth visual vocabulary. Check `style.css`'s current `.poster-review-*`
rules before adding new ones — some of what Phase 04 needs may already be styled.

### Known process notes from the first 3 phases (apply these to Phase 04 too)

- **Always hard-reload (`Ctrl+Shift+R`)** when browser-QA'ing a static/JS change —
  there's a real caching quirk (confirmed twice this session) where computed CSS is
  correct but the painted frame is stale until a hard reload. Don't mistake this for a
  CSS bug.
- **Grep for existing CSS classes before inventing new ones.** The Phase 03 sparkline
  bug (invented `.spark`/`.spark-row` with zero CSS backing, rendered as a broken solid
  black block) happened exactly because pitch-doc mockup class names got carried into
  real code without checking whether the real stylesheet already had a convention
  (`.sparkline-*`, dead but present) to reuse instead.
- **Every phase ships with real tests before commit**, mocking `docker_client`/`httpx`
  the same way `test_host.py`/`test_host_diagnostics.py`/`test_catalog_router.py` do -
  follow those three files as the house style for this project's FastAPI test patterns
  (login helper, service-key helper, `sys.modules["core.docker_client"]` mocking).
- **Full suite must stay green** — run `tests/control_panel/` in full before every
  commit, not just the new file's tests (a regression in an unrelated router has
  happened to other agents working this codebase before; cheap insurance).
- **Rebuild + recreate + browser-QA in both themes before every commit** — this project's
  standing practice for control-panel changes, not optional polish.

## Everything else from the original treatment that's still relevant

The treatment doc's risk table, the 20-program catalog research, and the phase-01
build-time/token estimates are all still accurate reference material — no need to
re-derive them, just re-fetch the artifact URL above if a future session needs the
full detail instead of this summary.
