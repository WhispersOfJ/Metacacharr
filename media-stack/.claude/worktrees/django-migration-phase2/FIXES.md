> **CLOSED AS MOOT — 2026-07-28.** BearMount was removed entirely this date (cutover to
> `nzbdav/nzbdav`, a maintained "super-fork" of the original NzbDAV lineage - see STACK.md's
> History), following a live investigation into a *different* issue (a Usenet provider
> connection/retention problem, not a FUSE bug). This investigation's fix (`asyncbuf-streaming-
> guard`, confirmed 2026-07-27) never had a chance to prove itself over real time before the
> app it was fixing was replaced. NzbDAV's actual FUSE mount is now a separate stock rclone
> sidecar (`nzbdav_rclone`), a different codebase with no confirmed equivalent bug — this
> record is kept as-is below for historical reference, not because the hang class is expected
> to recur. The automated mitigation endpoint this investigation built
> (`/api/bearmount/unstick-ffprobe-hang`) was removed along with BearMount, not ported.
>
> Original notes follow unchanged.

# BearMount FUSE read-hang — 2026-07-26 session notes

**2026-07-27 ROOT CAUSE CONFIRMED (via a live pprof goroutine dump, not theory)**: wired
`profiler_enabled: true` in `config/bearmount/config.yaml` (altmount already had `/debug/pprof`
routed, just gated behind that flag - no code change needed for this part) and captured a real
goroutine dump mid-hang. It showed the actual FUSE `Read()` goroutine parked in
`sync.Cond.Wait()` inside `AsyncReadBuffer.ReadAtContext` (`internal/fuse/backend/asyncbuffer.go`),
and the buffer's background `fill()` goroutine *also* parked in its own `sync.Cond.Wait()` -
same buffer instance, both permanently stuck, neither able to wake the other.

Mechanism: both frontier-wait loops in `ReadAtContext` (sequential-at-frontier and
near-frontier) omitted `a.streaming` from their wait condition. A concurrent `ReadAtContext`
call on the *same open handle* (the kernel can and does issue multiple in-flight reads per fd -
ffprobe's probe-then-seek pattern is exactly this) sees a non-sequential offset while the buffer
is streaming and calls `demoteLocked()`, which sets `a.streaming = false`, resets `a.filled = 0`,
and `Broadcast()`s. The waiting goroutine wakes, re-checks its *old* condition - which never
looked at `a.streaming` - sees `filled` still hasn't caught up to its offset, and parks again.
But `fill()` has itself parked waiting for a *new* promotion, and only a goroutine reaching the
probing-mode code path (not one stuck in this wait loop) can trigger that. Permanent deadlock,
unrelated to anything examined in the sections below - it doesn't touch `readFullContext`,
`GetReaderContext`, `mvf.mu`, or `downloadManager` at all, which is exactly why none of those
five rounds of instrumentation, across two sessions, ever caught it: it isn't in any of that code.

**Fix**: both wait loops now also exit when `a.streaming` goes false, falling through to the
existing probing/passthrough path - the same recovery the pre-existing "closed while waiting"
case already used, just reached from one more cause. `debrand/altmount-clean` commit `3130a4b6`.
Built as `altmount-local-fix:asyncbuf-streaming-guard` (includes the earlier `1b59596e`
`readFullContext` fix too - that one closed a real, separately-confirmed dead escape hatch, kept
even though it wasn't this hang's mechanism) and deployed live 2026-07-27. Watching for a real
recurrence before calling this closed for good and upstreaming as a PR.

---

**2026-07-27 EARLIER UPDATE (superseded by the above): the `readFullContext` fix below is real
but NOT sufficient** — a live
recurrence happened ~20 minutes after deploying it (two ffprobe D-state hangs,
`Spectral.2016...` and `Jurassic.World.Chaos.Theory...`, both past 2 minutes stuck) with
**zero log output whatsoever** for either file - no `readFullContext` timeout warning, no
`GetReaderContext` slow-warning, no `mvf.mu` wait warning. That absence is itself informative:
it proves the stuck code is upstream of every point instrumented or bounded across two sessions
now, most likely genuinely inside `hanwen/go-fuse`'s own request dispatch or the kernel/FUSE
boundary - the two pieces of "remaining unexamined territory" this doc already named and never
got to. bearmount's own FUSE mount died during/shortly after this occurrence (`transport
endpoint is not connected`, container gone) - recovered with the standard `sudo umount -l` +
recreate + cascade. Keep the `readFullContext` fix (it closes a real, separately-confirmed dead
escape hatch, see below) but **do not consider this hang solved** - next step is a real
goroutine dump via pprof (still not wired up) or reading `go-fuse`'s dispatch/request-pool
internals directly.

**A THIRD occurrence followed within the same watch window** (`Jurassic.World.Chaos.Theory.S02E06`),
with a cleaner signature worth recording: `downloadManager` DEBUG logs showed all 46 initially
scheduled segments finish downloading (`in_flight` draining 27→0) while `current_read` advanced
only from 0→1, then **total silence** — not one more log line of any kind, including the
`GetReaderContext`-took-`>10s` warning, which is logged unconditionally after that call returns
regardless of success or timeout. Its total absence, more than 3 minutes past the point that
warning should have fired if the call were even in flight, means the code isn't inside
`GetReaderContext` either — confirms (doesn't just suggest) that the stall is upstream of both
bounded points, at debug log level with nothing to show for it. bearmount itself then died a
*third* time, independently — not as a side effect of anything this session did to it.

**A real, separate control-panel bug found trying to recover from that third death**: the
2026-07-27 lazy-umount-retry fix (below) called `_recreate_container_via_sdk("bearmount")` a
second time on retry, and that function unconditionally re-`inspect_container`s the named
container to build its recreate config. Once the first attempt's `remove_container` has already
run, there is nothing left to inspect — the retry 404'd immediately regardless of whether the
umount itself worked, and the endpoint reported a useless "No such container: bearmount" instead
of actually recovering. Fixed by splitting `_recreate_container_via_sdk` into
`_capture_container_config` (inspect once) and `_recreate_and_start_from_config` (takes the
already-captured config, never re-inspects) — `_restart_bearmount_cascade` now captures once up
front and reuses that same captured config across every retry in the function. If bearmount is
already fully gone before the cascade even starts, there is still no way for this endpoint to
recover (no container left to capture from at all) - that now fails fast with a clear message
pointing at a host-side `docker compose up -d --force-recreate bearmount` instead of a confusing
404. Rebuilt and deployed live 2026-07-27.

**Net effect of this watch session**: two real control-panel bugs found and fixed (both
concrete, both confirmed against live failures, both worth keeping), one altmount-side fix
deployed and shown insufficient, and the actual root cause still open. Recovered from three
separate bearmount deaths by hand during this window - each time via the standard `sqlite3`
queue check + `sudo umount -l /mnt/bearmount` + `docker compose up -d --force-recreate
bearmount` + verify content + `--force-recreate` the 5 dependents + verify from inside each one.
That recipe held every time; nothing about tonight suggests it's unreliable, only that
bearmount is currently dying more often than before (three times in under 15 minutes of active
Radarr/Sonarr import traffic, vs. roughly one every few days before this).

Working notes for whoever picks this up next. Full blow-by-blow with all evidence lives in
`STACK.md` (search "recurring-hang" / "Occurrence #"); this file is the condensed version:
what's actually true right now, what's fixed, what isn't, and where to start.

## The bug

Radarr/Sonarr's own media-info probe (`ffprobe -probesize 50000000 ...`) against a 50GB+ REMUX
occasionally deadlocks the FUSE read in D-state (kernel-confirmed via `/proc/<pid>/stack`:
`filemap_read` → `folio_wait_bit_common`, i.e. genuinely waiting on bearmount's userspace daemon
to answer, not a real disk/network stall).

**Confirmed signature** (`bearmount`'s own debug logs, `downloadManager` component): every
segment `downloadManager` prefetches finishes downloading successfully (`in_flight` drains
cleanly to 0), but the reader's consumption position (`current_read`) never advances past
wherever it happened to stall (varies: 0, 1, 6 across different occurrences — not tied to one
segment's content). Nine occurrences same day, always a 50GB+ REMUX, always via that exact
`ffprobe` invocation.

## What's fixed vs. not

Three *different* bugs got found and fixed today — all real, all verified, none of them the one
above:

1. **`sync.Cond` lost-wakeup** in `UsenetReader`'s download-scheduling loop — `Signal()` called
   without holding the mutex the condition variable is tied to. Fixed (locked properly).
2. **Unbounded `budget.Acquire` wait** — the import-connection-budget semaphore had no timeout.
   Bounded to 5 minutes with a warning log.
3. **Unbounded `poolGetter()` wait** — `pool.manager.GetPool()` could theoretically block on the
   manager's write lock. Bounded to 30s defensively (never confirmed as *this* hang's mechanism).

All three are real fixes worth keeping. **None of them resolved the actual recurring hang above**
— it kept recurring after all three were deployed, with identical symptoms each time.

## The hang itself: five instrumentation rounds, all negative

Traced the exact stuck call as far as `UsenetReader.Read()`'s call to
`segment.GetReaderContext()` for the segment at `current_read`. Bounded that to 2 minutes
(`readerctx-timeout` image) — a real, verified partial improvement (one case where `current_read`
advanced past its first segment for the first time ever), but not a fix: the *next* occurrence
proved the actual stall doesn't even reach that call.

Four independently-instrumented candidate points, checked across five separate diagnostic
rounds, **all stayed silent** through multiple confirmed reproductions (D-state 5-9+ minutes,
well past every timeout):

- `UsenetReader.Read()` → `segment.GetReaderContext()` (bounded to 2min, `readerctx-timeout`)
- `MetadataVirtualFile.ReadAtContext`'s shared-reader `Read` loop
- `MetadataVirtualFile.mu` lock *acquisition* itself (not just work after acquiring it —
  `Close()`'s own comment already documented this lock "can be held for the full
  segment-download latency")
- `readFullContext`, which backs a completely separate "ephemeral" reader path
  (`createReaderAtOffset` + a fresh one-off reader per call) that `ffprobe`'s non-sequential
  probing plausibly hits instead of the sequential/shared path every other fix targeted

**Conclusion: the actual stuck code is upstream of everywhere examined today.** Remaining
unexamined territory:
- The `hanwen/go-fuse` library's own request dispatch / goroutine pool (never touched — every
  fix today started from `Handle.Read()` downward, not from the library's own internals).
- The kernel/FUSE-protocol boundary itself.

## Root cause, confirmed 2026-07-27

Found by reading `hanwen/go-fuse`'s vendored source instead of adding more instrumentation —
the "kernel/FUSE-protocol boundary" flagged above as unexamined territory.

`ctx` passed into every one of these handlers (`ReadAtContext`, `readFullContext`,
`GetReaderContext`'s caller in `UsenetReader.Read`) traces back to `*fuse.Context`
(`vendor/github.com/hanwen/go-fuse/v2/fuse/context.go`), which `rawBridge.Read`
(`vendor/.../fs/bridge.go`) constructs fresh per FUSE request and passes straight through as the
`context.Context` argument — it satisfies the interface, but it isn't a real one:

- `Deadline()` unconditionally returns `(time.Time{}, false)` — no deadline, ever.
- `Done()`/`Err()` are wired to a `<-chan struct{}` that only closes when the kernel sends the
  `FUSE_INTERRUPT` opcode for that specific request (`protocol-server.go`'s
  `interruptRequest`) — and the kernel only sends `FUSE_INTERRUPT` when a **signal** arrives for
  the process blocked in the `read()` syscall.

A process stuck in **D-state** (uninterruptible sleep — confirmed via `/proc/<pid>/stack` on
every single occurrence of this hang) cannot receive that signal by definition. So `ctx.Done()`
in `readFullContext` — the exact escape hatch it was written to use — could never fire for the
one case it existed to catch. This is also why five rounds of instrumentation on downstream
waits (`GetReaderContext`, `budget.Acquire`, `poolGetter`) never caught anything firing: those
are real, independently-bounded fixes, but the actual stall was in `readFullContext`'s ephemeral
reader path (`createReaderAtOffset` + a fresh one-off reader per call — exactly the branch
`ffprobe`'s non-sequential probing hits), waiting on a cancellation signal that structurally
could never arrive.

**Fix** (`javi11/altmount` fork, `debrand/altmount-clean`, commit `1b59596e`):
`readFullContext` now derives its own `context.WithTimeout(ctx, 2*time.Minute)` instead of
trusting the inherited FUSE-request context to ever cancel — the same pattern `GetReaderContext`
already used. Since this call runs with `mvf.mu` held for its entire duration, this also
unblocks every other read queued behind it on the same file handle (shared reader, AsyncReadBuffer
fill goroutine) once it fires. `go build`/`vet`/`test` all pass. Built as
`altmount-local-fix:fuse-ctx-independent-timeout` and deployed live 2026-07-27 — **confirmed a
sixth negative round**, see the update at the top of this doc. Worth keeping regardless (real
fix for a real dead escape hatch, just not this hang's mechanism).

**Also fixed live 2026-07-27, a second, separate control-panel bug found during this same
incident**: `_restart_bearmount_cascade`'s lazy-umount retry only ran when the *first* recreate
succeeded but came back with an empty mount — if the first `_recreate_container_via_sdk` call
itself threw (confirmed live: it can, when the host mount is already wedged going in, not just
racing a fresh umount), the route just called `fail()` immediately with bearmount already
removed and no recovery attempt at all. Now retries via the same lazy-umount dance in that case
too. Fixed in `control-panel/app.py`, rebuilt and deployed.

Getting further needs either a real Go goroutine dump (no `pprof` endpoint wired up currently —
adding one and getting a live SIGQUIT-style dump was considered but not attempted, since it kills
the process along with whatever mount state), or reading `go-fuse`'s own source for how it
dispatches/pools read requests.

## Standing mitigation (works, ship it)

Six-for-six occurrences today cleared cleanly with zero data loss via: identify the file
(`ps -eo stat,pid,etime,args` for a D-state `ffprobe`/`ffmpeg` referencing
`/mnt/bearmount-import/`), blocklist its release in Radarr/Sonarr
(`DELETE /queue/{id}?removeFromClient=true&blocklist=true&skipRedownload=false`), then the
standard bearmount recreate + 5-dependent cascade.

**This is now automated**: `POST /api/bearmount/unstick-ffprobe-hang` (control-panel,
`app.py`) does the whole thing — detect, blocklist, recreate, cascade, verify. Pass `force=true`
to skip the import-queue-empty gate if needed.

**Now exercised against real live hangs (2026-07-26), not just a clean state.** Two real
occurrences the same day exposed a gap: bearmount sometimes comes back "healthy" after a plain
recreate with its own FUSE mount still wedged (`/mnt/bearmount/movies` stays empty) — the
endpoint correctly refused to touch the 5 dependents in that state (avoiding a repeat of the
2026-07-25 mass-deletion trigger) but originally required a manual `sudo umount -l
/mnt/bearmount` + second recreate to actually clear it. That retry is now automated too, via
`_host_lazy_umount()` using `nsenter --target 1 --mount` — control-panel already runs with
`pid: host` for the Plex Force Unstick feature, so PID 1 in its own `/proc` is the host's real
init, and `nsenter` through it reaches the host mount namespace with no new bind-mount needed.
This did require adding `cap_add: SYS_PTRACE` to control-panel's compose service (deliberate,
non-trivial privilege widening — ptrace access to any host process, not just this one mount
namespace file — accepted 2026-07-26 for this) and `util-linux` to the Dockerfile (provides
`nsenter`).

Also found and fixed live during that same test: `_wait_for_bearmount_content()` held a single
`Container` object across its whole poll loop. If anything recreates bearmount again while the
loop is running, that handle goes stale mid-poll and crashed the whole route with an unhandled
`docker.errors.NotFound` (500) instead of failing cleanly. Now re-fetches by name every
iteration and swallows `NotFound` as "not ready yet."

Also fixed the same day: `_restart_bearmount_cascade()` (the function every unstick/restart-cascade
route already used) was calling `.restart()` on the five FUSE-dependent containers instead of a
real recreate — the exact stale-mount bug documented below, just never noticed because nothing
had exercised that code path against a fresh bearmount mount recently. Now uses
`_recreate_container_via_sdk()` for dependents too, matching manual practice.

## Operational gotchas found/relearned today (also in CLAUDE.md now)

- **Always `--force-recreate` bearmount's dependent cascade, never `restart`.** `restart` reuses
  the container's existing mount namespace and never picks up bearmount's fresh FUSE mount —
  every dependent silently serves a stale handle despite Docker reporting healthy.
- **Settle-pause before touching dependents.** After recreating bearmount, verify the host mount
  is actually live (`ls /mnt/bearmount` succeeds) before recreating any dependent — racing this
  reproduces the same stale-handle problem from the other direction.
- **A "double-recreate" happened twice**, unexplained: `--force-recreate bearmount` alone
  sometimes results in bearmount tearing itself down and remounting a second time within ~10s of
  the first, and the second attempt's own FUSE mount fails (`fusermount3: user has no write
  access to mountpoint`, a transient post-unmount state). Recovery: `sudo umount -l
  /mnt/bearmount` then recreate again. Never diagnosed — a `docker events` capture attempt during
  a live repro hung instead of yielding an answer. Worth a dedicated look if it recurs.
- **Fish functions (`stack-*`) aren't in Claude Code's own shell** — use `fish -c "stack-foo ..."`
  or call the control-panel API directly.
- **Root cause found and fixed, 2026-07-27**: `unstick-ffprobe-hang` ran live against a real hang,
  hit the "mount still empty after first recreate" branch, called `_host_lazy_umount`, then tried
  a second `_recreate_container_via_sdk("bearmount")`. That helper's `create_container` call raced
  the kernel still settling the just-completed umount — bind-mount source stat still reported
  "transport endpoint is not connected", `create_container` raised `APIError`, and because
  `remove_container` had already run with no rollback, bearmount was left with **no container at
  all** (not unhealthy — gone), mount still wedged. `_restart_bearmount_cascade` correctly refused
  to touch the 5 dependents (they were untouched, all healthy on their pre-outage mount views) but
  the 502 gave no indication bearmount itself had been deleted. Found via `docker compose ps -a`
  showing bearmount absent entirely, then `dockerd` journal's `task-delete` event at 04:01:10
  correlated to control-panel's own access log (`POST /api/bearmount/unstick-ffprobe-hang ...  502
  Bad Gateway` at the same timestamp). Fixed by retrying `create_container` up to 5x with a 2s
  backoff inside `_recreate_container_via_sdk` instead of raising on the first transient failure —
  see the function's docstring/comment in `app.py`. Recovered manually this session: `sudo umount
  -l /mnt/bearmount` + `docker compose up -d --force-recreate bearmount`, verified mount content,
  then `--force-recreate` on all 5 dependents.
- Debug logging for bearmount is `config/bearmount/config.yaml`'s top-level `log:` → `level:`
  field — *not* the `log_level:` field under the disabled rclone-mount section higher up in the
  same file, which looks similar but does nothing (rclone mount is disabled in this config).

## Where things are left

- `docker-compose.yml`'s `bearmount` service points at `altmount-local-fix:ephemeral-diag` — the
  latest diagnostic image (includes all three real fixes + all instrumentation, all negative
  results still logging warn-on-slow if any of the four points ever does fire). Safe to leave
  running; it's diagnostic-only beyond the three real fixes.
- All work pushed to `origin/debrand/altmount-clean` on `WhispersOfJ/altmount` (a real GitHub
  fork of `javi11/altmount`) — commit `e6be12b5` is the tip. One rebase happened mid-session to
  strip an accidentally-vendored third-party Slack webhook secret (`go mod vendor` pulled in a
  dependency's own CI config file) that GitHub's push protection caught before it ever reached
  the remote — nothing of ours was exposed.
- `control-panel/app.py` has the new endpoint and the `_restart_bearmount_cascade` fix, built and
  deployed, but **not yet git-committed in this repo** — do that next session (or now, if you're
  reading this same-day).
- PR #801 on `javi11/altmount` (an unrelated earlier fix, immediate-repair-via-health-queue) was
  also finished and pushed this session — separate from everything above.
