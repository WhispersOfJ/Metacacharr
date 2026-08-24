# PRIORITY: Address security issues immediately

Reviewed repo: `nzbdav/nzbdav` (the super-fork this stack's `docker-compose.yml`
actually runs as `ghcr.io/nzbdav/nzbdav:latest`), synced to upstream `main`
HEAD at `fd95e6b` (release 0.9.4, 2026-07-31).

**Promise:** the top-ranked security finding below will be verified FIRST,
before any other finding in this list is acted on. Do not defer this check.

**Status, 2026-07-31: FIXED locally, not upstreamed.** The CreateAccountController
TOCTOU (single-admin race) is patched in this local clone - filtered unique index
`IX_Accounts_SingleAdmin` + application-level pre-check + DbUpdateException
backstop, all covered by `tests/NzbWebDAV.Tests/Api/CreateAccountControllerTests.cs`
(4 new tests, full suite 1420/1420 passing). This patch has NOT been submitted
upstream to `nzbdav/nzbdav` as a PR - do that explicitly if you want the fix to
outlive this local clone, since `sync-nzbdav-upstream.sh` will discard it on
the next `git reset --hard origin/main`.

Note on a separate, unrelated project: `nzbdav-dev/nzbdav` (the original,
now-superseded upstream this fork descends from) disclosed an unauthenticated
auth-bypass affecting its versions 0.2.46-0.6.1, patched 2026-03-18 (no CVE ID
assigned; fixed builds carry a `+260317` version suffix). No GHSA/CVE record
was found for it (checked `gh api repos/nzbdav-dev/nzbdav/security-advisories`
- empty). This deployment does not run that fork - `CHANGELOG.md` here shows
this fork (`nzbdav/nzbdav`) has its own independent, more recent auth-hardening
history (constant-time key comparison, session invalidation on credential
change, timing-oracle fix, `funnel frontend auth through middleware`) - so
that specific advisory is not directly applicable, but is worth spot-checking
this fork's own middleware-auth commit (`eb71ebf`) actually covers every
route, per Finding 1 below.

## Before touching anything

1. Re-sync: `sh vendor/sync-nzbdav-upstream.sh` — confirm you're reviewing
   current HEAD, not a stale clone.
2. Re-read the findings list below in order (least -> most severe) so you
   have full context before making changes.

## Fix-verification checklist (run after each fix, not just once at the end)

- [ ] Confirm the running container's version: `docker inspect nzbdav --format
      '{{index .Config.Labels "org.opencontainers.image.version"}}'` (or
      check `/api/get-config` if the label isn't set) and compare against
      `vendor/nzbdav/version.txt` / the CHANGELOG entry for the CVE fix.
- [ ] Re-run the repo's own test suite: `cd vendor/nzbdav/backend && dotnet
      test` (see "Repo health" section of the findings report for whether
      this currently passes clean).
- [ ] Re-scan dependencies for known CVEs: `dotnet list backend package
      --vulnerable --include-transitive` and `cd frontend && npm audit`.
- [ ] Re-review the exact changed code path (diff the specific file/line
      range cited in the finding) - don't just trust that a version bump
      fixed it; confirm the vulnerable code is actually gone.
- [ ] If the fix touches auth/session handling: manually verify a request
      with no/invalid credentials is rejected (`curl -i` against the
      affected endpoint, expect 401/403, not 200).
- [ ] Re-check this stack's own `.env`/`config/nzbdav/` for any credential
      that may have been exposed while the bug was live, and rotate it if
      the exposure window overlaps this deployment's uptime.
