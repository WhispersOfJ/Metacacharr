---
name: trash-guides-applier
description: Apply TRaSH-Guides recommended quality profiles and custom formats to Radarr and Sonarr via their REST APIs, using the JSON profile definitions in profiles/. Use when the user asks to set up or refresh quality profiles following TRaSH-Guides, or add a custom format (e.g. HDR10+, remux-tier scoring). Trigger phrases: "apply trash guides profiles", "set up quality profiles", "add this custom format", "refresh radarr/sonarr profiles".
---

# TRaSH-Guides Applier

Recyclarr (this stack's former scheduled TRaSH-Guides sync daemon) was removed entirely in
v11.2.0, along with every non-"ANY" quality profile on both apps — this skill is now the
only way to apply TRaSH-Guides profiles/custom-formats in this stack, not a fallback for
gaps in a scheduled sync. There is no daemon running in the background to conflict with or
defer to.

## Profile files

- `profiles/radarr-profiles.json` — quality profiles + custom formats for Radarr,
  following TRaSH-Guides' movie recommendations (WEB-DL/Remux tiering, HDR bonus scoring).
- `profiles/sonarr-profiles.json` — same shape for Sonarr (episode quality tiering).

Each file has the shape:
```json
{
  "quality_profiles": [
    {"name": "HD Bluray + WEB", "upgrade_allowed": true, "cutoff": "WEB 1080p", "items": [...]}
  ],
  "custom_formats": [
    {"name": "HDR10+", "score": 30, "specifications": [...]}
  ]
}
```

## Usage

```bash
python3 applier.py apply radarr --profiles profiles/radarr-profiles.json
python3 applier.py apply sonarr --profiles profiles/sonarr-profiles.json
python3 applier.py diff radarr --profiles profiles/radarr-profiles.json   # what would change
python3 applier.py list-current radarr                                    # what's live right now
```

Auth via the same `RADARR_URL`/`RADARR_API_KEY` (and Sonarr equivalent) environment
variables as `arr-config-sync` — no separate credential config.

## Safety rules

- `apply` is additive/updating only by matching custom-format and quality-profile `name`:
  it creates missing ones and updates changed ones, but never deletes a profile/format
  that exists live but isn't in the local JSON — a user may have a profile that's
  intentionally not TRaSH-standard.
- Always run `diff` before `apply` when the profile JSON files have been hand-edited,
  to catch typos before they hit a live Radarr/Sonarr instance.
