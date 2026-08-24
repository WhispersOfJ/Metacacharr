# Re-enabling Anime (Movies) — Design

**Date:** 2026-08-06
**Status:** Approved — both branches to be fully specced, branch decision deferred to implementation time.

## Background

Anime support was fully removed in v10.19.0 (commit `182d8d1`), by explicit request: 122
Radarr movies + 159 Sonarr series (deleted with files), both dedicated Plex libraries, both
root folders, the `[Anime] Remux-1080p` quality profile and its 33 custom formats, Zurg's
anime routing groups, the AllDebrid anime rclone mount, Kometa's Anime library blocks +
MyAnimeList creds, `sort-anime-movies.py` + its systemd units, control-panel's anime refs,
and 8 anime-relevant Prowlarr indexers. A live Sonarr Trakt import list that would have
silently re-added anime series was also found and removed.

Since that removal, the stack itself changed underneath this history in ways that make the
old setup non-restorable as-is:

- **Recyclarr removed entirely** (v11.2.0), along with every non-"Anything" quality profile
  on both Radarr and Sonarr. The tool that used to keep `[Anime] Remux-1080p`'s ~33 custom
  formats in sync with TRaSH-Guides automatically no longer exists anywhere in the stack.
- **Debrid/torrent removed entirely** (v11.0.0). The old anime pipeline ran through Zurg +
  an AllDebrid rclone mount — that entire path is gone. The stack is Usenet-only now via
  NzbDAV.
- **Prowlarr is down to 3 Usenet indexers**, all rate-limited to 100 queries/50 grabs/day
  each, shared across everything the stack already searches for (confirmed 2026-08-04).

This design re-plans anime support against the *current* stack, not the deleted one.

## Scope (decided)

- **Anime movies only.** Anime TV series (Sonarr) are explicitly out of scope for this round
  — can be a separate follow-up design if wanted later. This sidesteps the historical Sonarr
  pain points entirely: absolute-episode-numbering conflicts, the 159-series migration, and
  the Trakt import-list risk that was found live during removal.
- **No torrent client, no debrid, no VPN.** Ruled out explicitly — Usenet-only stays Usenet-only.
- **No Kometa / MyAnimeList integration.** Kometa was just moved to manual-only runs
  (`784a579`) and stays untouched. Anime movies get standard Plex/TMDB metadata. Can be
  layered in later as its own small project.
- **Dedicated Plex library** ("Anime Movies"), not merged into the existing Movies library.

## Common ground — applies to both branches

These pieces are identical regardless of which branch gets implemented, and should be built
once, first, before branching:

1. **New root folder:** `/data/anime-movies`, freshly created (the old path was deleted with
   the rest in the removal).
2. **New Plex library:** "Anime Movies", using Plex's standard Movie agent (no anime-specific
   Plex agent exists or is needed) pointed at `/data/anime-movies`.
3. **No automatic sweep/sort script.** The old `sort-anime-movies.py` + systemd timer existed
   only because anime movies landed in the *main* movies library first and had to be
   post-hoc matched and moved out by Plex's own "Anime" tag — a real finding from 2026-07
   was that **Radarr/TMDB has no "Anime" genre at all**, so this could only ever be a
   post-import sweep, never a pre-import filter. That constraint no longer forces a sweep
   script: because anime gets its own root folder from day one, the destination is chosen
   **at add-time** (pick `/data/anime-movies` in Radarr's UI, or route Overseerr/Jellyseerr
   requests there if that integration exists). This eliminates an entire piece of
   infrastructure the old setup needed, with no functional loss.
4. **Indexers:** reuse the existing 3 Usenet indexers (NZBgeek, DrunkenSlug, NzbPlanet) as-is.
   No anime-specific indexer exists to add without a torrent client. Expectation to set now:
   general Usenet indexers carry theatrical/mainstream anime (Ghibli, Shinkai, major
   franchises) reasonably well, but will be thinner than a torrent scene community for
   obscure OVAs, batches, or older/rare titles. This is a real coverage trade-off inherent to
   staying Usenet-only, not a bug to fix later.
5. **Query-budget guardrail.** All 3 indexers share a combined 100 queries/50 grabs/day cap
   with everything else already running on the stack. A bulk backlog import of ~100+ anime
   movies at once would burn that cap in one day. Mitigation: enable RSS sync (near-zero
   query cost) for ongoing new releases immediately; do any backlog catch-up in small manual
   batches over several days, and watch `stack-queue-status`/indexer grab counts before
   scaling up.
6. **Custom formats maintained by hand.** Since Recyclarr is gone stack-wide and no exception
   is being carved out for anime, anime-relevant custom formats (dual-audio preference,
   uncensored preference, sub-group hygiene) get added via the existing
   `trash-guides-applier` skill/JSON — the same manual pattern used for the Criterion
   Collection format (2026-08-06, id 66 on the live "Anything" profile). This applies
   identically in both branches; the only difference is *which* quality profile they're
   scored into.

## Branch A — Shared instance (no new software)

Anime movies live inside the **existing** Radarr container. Nothing new is deployed.

- **Root folder:** `/data/anime-movies` added as a *second* root folder on the existing
  Radarr, alongside `/data/movies`.
- **Quality profile:** extend the single live "Anything" profile with the anime custom
  formats (dual-audio, uncensored, sub-group hygiene), scored additively — same mechanism as
  Criterion Collection, no new profile created.
- **Bazarr / Unpackerr / NzbDAV / Prowlarr:** zero new wiring required. They already watch
  "the" Radarr instance as a whole; a second root folder inside it is invisible to them as a
  distinct integration point.
- **Control Panel / skills (`docker-compose-manager`, `health-monitor`, `arr-config-sync`):**
  no changes needed — they already track the one Radarr instance.
- **Effort:** smallest possible. One root folder, one Plex library, a handful of custom
  formats, done in an afternoon.
- **Trade-off:** anime and live-action movies share fate on every instance-wide setting —
  restarts, any future profile change, and specifically **quality *definitions*** (the
  file-size ranges per quality tier). The 2026-07 single-instance research explicitly found
  these are instance-wide, not per-profile, and documented *not* applying TRaSH's
  anime-specific size ranges as a deliberate, load-bearing trade-off to avoid silently
  breaking sizes for the entire non-anime library. The same constraint applies here: anime
  movies get the *existing* quality definitions, not TRaSH's anime-tuned ones.

## Branch B — Dedicated instance ("new software": a second Radarr container)

A new `radarr-anime` container (same `hotio/radarr` image, isolated `config/radarr-anime/`
volume) runs alongside the existing Radarr, fully independent.

- **Root folder:** its own `/data/anime-movies`, config'd only on this instance.
- **Quality profile:** built cleanly around TRaSH's anime custom-format set (BD/Web tiers,
  dual-audio, uncensored, sub-group hygiene) from scratch, with **its own quality
  *definitions*** (file-size ranges) if wanted — the exact isolation the single-instance path
  in Branch A explicitly gives up.
- **Naming scheme:** independent from the main Radarr's, can follow anime-community
  conventions if desired without touching the main library's naming.
- **Integration checklist** (drawn directly from the 2026-07-18 removal commit's own
  findings about what a dedicated instance touches — these are the exact spots that were
  found live and had to be cleaned up after the fact last time, so they're called out
  up front this time instead of discovered later):
  - **Prowlarr** → add `radarr-anime` as a synced app alongside the main Radarr, same 3
    indexers, independent per-app sync profile.
  - **Unpackerr** → add a `[radarr_anime]` config block so extracted archives get imported
    into the new instance.
  - **NzbDAV's Repairs tab** → confirm it recognizes and lists the new instance's download
    category correctly.
  - **Bazarr** → add a second Radarr connection pointed at `radarr-anime` for subtitle
    coverage (Bazarr has no library of its own; it only watches connected apps).
  - **Control Panel (`control-panel/app.py`, `ARR_APPS`)** → register the new instance so
    it appears in the dashboard/queue views instead of being invisible to the UI.
  - **`docker-compose-manager`, `health-monitor`, `arr-config-sync` skills** → add the new
    instance to each skill's app list; otherwise they silently skip it in their sweeps.
  - **Request manager (Seerr), if wired** → add a second Radarr connection scoped to the
    anime root folder/profile, per the `request-manager-integrator` skill's pattern for a
    second quality-profile-specific connection.
- **Effort:** materially larger than Branch A — a new container plus roughly 7 integration
  points to wire up correctly (vs. Branch A's ~0).
- **Trade-off:** ongoing maintenance surface. One more container to keep updated, one more
  config set to keep in sync, one more thing that can silently drift out of the fleet's view
  if any of the 7 integration points above is missed — precisely the class of gap the 2026-07
  audit found (Unpackerr, NzbDAV's Repairs tab, and Maintainerr were all missed on the first
  pass back then, before being caught by a deliberate cross-check).

## Decision context for whoever implements this

- 2026-07's own research (deleted `PLAN.md`, commit `6ee0ad4`) already concluded that
  TRaSH-Guides' own guidance treats a single instance with a second quality profile as fully
  supported, not a workaround — this favors Branch A as the default unless the quality
  *definitions* isolation or future growth into anime series specifically motivates Branch B.
- Branch B is the right call specifically if: (a) TRaSH's anime-tuned file-size ranges matter
  enough to be worth the isolation, or (b) there's a concrete plan to extend into anime
  *series* later and standing up the isolation now avoids a second migration.
- Whichever branch is chosen, do the "Common ground" section first — it's identical work
  either way and de-risks the decision by getting the root folder/library/indexer pieces
  proven out before committing to shared-vs-dedicated.

## Testing / verification plan

- After root folder + Plex library are live: add one known-available anime movie manually,
  confirm it searches, grabs, imports, and shows up in the "Anime Movies" Plex library with
  correct metadata — before doing any bulk add.
- After custom formats are added: verify via the live `customformat` API (same pattern used
  to verify Criterion Collection, id 66) that scores are attached to the correct quality
  profile (existing "Anything" profile for Branch A, the new anime profile for Branch B).
- Watch indexer grab/query counts for several days after enabling RSS sync, before doing any
  backlog catch-up batch.
- If Branch B: verify each of the 7 integration checklist items individually — don't assume
  "the container is running" means "the fleet sees it."

## Explicitly out of scope for this design

- Anime TV series (Sonarr) — separate future design if wanted.
- Torrent/debrid/VPN of any kind.
- Kometa / MyAnimeList metadata integration.
- Automatic re-sorting/sweep tooling of any kind (superseded by add-time root-folder choice).
