#!/usr/bin/env python3
"""Long-running watchdog for Control Panel's own /api/plex/scan-health
endpoint (see app.py's plex_scan_health() and the Plex Health section in
STACK.md) - that endpoint is stateless per call by design ("the frontend
keeps its own ring buffer"), and in practice the frontend only uses that
history for sparklines, not for actually detecting a stuck scan. Nothing
in this stack alerts or acts if nobody has the dashboard open. This script
is the thing that does: polls scan-health on an interval, tracks scan
progress across polls itself, and distinguishes the three failure classes
already documented in STACK.md's landmines section rather than treating
every non-healthy state the same:

  1. Genuine FUSE/D-state hang (dstate_threads non-empty or mount_ok is
     False) - alert only, no auto-restart. Tier 2 (mount-cascade restart)
     and Tier 3 (unstick) were both control-panel API endpoints
     (/api/plex/restart-cascade, /api/plex/unstick) that got removed along
     with BearMount, 2026-07-28 - that cascade-restart logic now lives in
     the docker-compose-manager Claude Code skill, which this headless
     script has no way to invoke. A hard hang now just alerts; a human
     runs the cascade restart via that skill or by hand.
  2. SQLite lock contention ("busy database" errors in the recent log
     tail) - alert, auto-trigger Tier 1 (plain container restart). Using
     the mount cascade here would be pointless risk for a problem it
     doesn't fix (STACK.md: "a plain docker compose restart plex clears
     it without any mount-cascade risk").
  3. Plain scan-progress lag: a library scan activity is present but its
     progress hasn't advanced across polls. Alerted past
     SCAN_LAG_ALERT_SECONDS; only auto-restarted (Tier 1) if it's still
     stuck past SCAN_LAG_RESTART_SECONDS, since a real large scan can
     legitimately sit at one percentage for a while. Suppressed entirely
     while scan-health's own analysis_active flag is set (see below) -
     stalled progress fully explained by real analysis work isn't lag.

Two more things factored in, added 2026-07-25 after live incidents exposed
both as real gaps:

  - Analysis delay: Plex's Media Analyzer processes newly-imported files in
    fixed ~30s on-the-fly batches (confirmed live: 8/8 observed "Background
    analysis completed" events read exactly 30.0 seconds - a scheduled
    batch window, not a variable timeout), and legitimately leaves no
    library-scan progress movement and no live scanner process between
    those cycles. Before this, that looked identical to a real stall.
    scan-health's own analysis_active field (see app.py's _plex_log_tail)
    now feeds classify() directly so real analysis work never gets
    misread as scan_lag.
  - Poll timeouts: a single slow/failed poll to scan-health no longer goes
    unremarked - CONSECUTIVE_POLL_FAILURE_ALERT tracks a run of failures
    and alerts once it's sustained, distinguishing "the endpoint was slow
    once" (expected under load, per api_get's own 30s headroom) from "the
    endpoint has been unreachable for multiple minutes" (worth knowing
    about on its own, independent of whatever scan-health itself would
    have reported).

Every auto-restart is edge-triggered and cooldown-gated (RESTART_COOLDOWN_
SECONDS) so a still-unhealthy container doesn't get restarted every poll.
Recovery is reported once, the same way scripts/check-container-health.sh
reports container recoveries.

Run by systemd/stack-plex-health-monitor.service - a long-running listener,
not a timer, since 30-second-scale lag detection needs state carried
between polls more often than a timer's minimum practical interval allows.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent
CONTROL_PANEL_URL = "http://localhost:8420"

POLL_INTERVAL_SECONDS = 15  # matches the dashboard's own Plex Health poll cadence
SCAN_LAG_ALERT_SECONDS = 30
SCAN_LAG_RESTART_SECONDS = 90  # 3 consecutive stuck polls before auto-restarting
RESTART_COOLDOWN_SECONDS = 600  # don't re-trigger an auto-restart more than once per 10 min
CONSECUTIVE_POLL_FAILURE_ALERT = 4  # ~4 poll intervals of sustained unreachability before alerting


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


DISCORD_WEBHOOK_URL = env_get("DISCORD_WEBHOOK_URL")
HOST_LABEL = env_get("HOST_IP") or "Stack"
# Every control-panel route this script touches sits behind
# current_user_or_service (core/security.py), which accepts a session cookie
# or this key. A daemon has no session, so without the header every poll
# 401s - which the retry logic below reads as "scan-health is unreachable",
# so the watchdog alerts about the control panel instead of watching Plex.
# Mirrors what fish-functions/__stack_api.fish sends on every call.
SERVICE_API_KEY = env_get("CONTROL_PANEL_SERVICE_API_KEY")
DISCORD_RED = 0xED4245
DISCORD_ORANGE = 0xFEE75C
DISCORD_GREEN = 0x57F287


def notify_discord(message, level="info"):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "changeme":
        print(f"[{level}] {message}")
        return
    title = {"error": "\U0001F534 Plex Health", "warn": "\U0001F7E1 Plex Health"}.get(level, "\U0001F7E2 Plex Health")
    color = {"error": DISCORD_RED, "warn": DISCORD_ORANGE}.get(level, DISCORD_GREEN)
    body = json.dumps({
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "footer": {"text": HOST_LABEL},
        }]
    }).encode()
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "media-stack-plex-health-monitor/1.0"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except urllib.error.URLError as e:
        print(f"notify_discord failed: {e}", file=sys.stderr)


def api_headers():
    headers = {"User-Agent": "media-stack-plex-health-monitor/1.0"}
    if SERVICE_API_KEY:
        headers["X-Api-Key"] = SERVICE_API_KEY
    return headers


def api_get(path):
    # scan-health chains several _bounded_exec calls (see app.py) that can
    # each take up to their own individual timeout when Plex's container is
    # genuinely slow/wedged - confirmed live this session at ~15s for a
    # single poll. 30s gives real headroom above that worst case rather
    # than treating the endpoint's own documented slow-path as a poll
    # failure.
    req = urllib.request.Request(
        f"{CONTROL_PANEL_URL}{path}",
        headers=api_headers(),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def api_post(path):
    req = urllib.request.Request(
        f"{CONTROL_PANEL_URL}{path}", data=b"",
        headers=api_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return True, json.load(r).get("message", "ok")
    except urllib.error.HTTPError as e:
        detail = json.load(e).get("detail", {})
        return False, detail.get("message", str(e))
    except (OSError, urllib.error.URLError) as e:
        return False, str(e)


def scan_progress(data):
    for a in data.get("activities", []):
        if a.get("type") == "library.update.section":
            return a.get("progress")
    return None


def classify(data):
    """Returns one of None (healthy), 'hard_hang', 'busy_db', or 'scan_lag'
    for the current poll alone - lag duration is tracked by the caller
    across polls, not here."""
    if data.get("dstate_threads") or not data.get("mount_ok", True):
        return "hard_hang"
    if data.get("recent_busy_db_errors", 0) > 0:
        return "busy_db"
    if data.get("analysis_active"):
        # Real Media Analyzer work in progress (see the module docstring)
        # fully explains flat scan progress / no live scanner process -
        # never classify this as scan_lag, no threshold involved.
        return None
    if scan_progress(data) is not None or data.get("state") in ("scanning", "stalled_suspected"):
        return "scan_lag"
    return None


def main():
    last_progress = None
    last_progress_ts = time.time()
    lag_started_ts = None
    active_alert = None  # currently-alerted failure class, or None
    last_restart_ts = 0.0
    consecutive_poll_failures = 0

    notify_discord("Plex health monitor started.", "info")

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            parsed = api_get("/api/plex/scan-health")
            data = parsed.get("detail", parsed)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
            # OSError covers a bare TimeoutError, which urlopen can raise
            # directly (not wrapped in URLError) on a read timeout - hit
            # live against a genuinely slow scan-health response. A failed
            # poll should never crash this daemon; just skip the cycle -
            # but a SUSTAINED run of these (unlike one-off, expected-under-
            # load slowness) is worth its own alert, tracked below rather
            # than reported on every single occurrence.
            consecutive_poll_failures += 1
            print(f"scan-health poll failed ({consecutive_poll_failures} in a row): {e}", file=sys.stderr)
            if consecutive_poll_failures == CONSECUTIVE_POLL_FAILURE_ALERT and active_alert != "poll_unreachable":
                active_alert = "poll_unreachable"
                notify_discord(
                    f"scan-health has failed to respond for {consecutive_poll_failures} consecutive polls "
                    f"(~{consecutive_poll_failures * POLL_INTERVAL_SECONDS}s) - last error: {e}", "warn")
            continue

        if consecutive_poll_failures >= CONSECUTIVE_POLL_FAILURE_ALERT:
            notify_discord(f"scan-health responding again after {consecutive_poll_failures} failed poll(s).", "info")
        consecutive_poll_failures = 0
        if active_alert == "poll_unreachable":
            active_alert = None

        progress = scan_progress(data)
        now = time.time()
        if progress != last_progress:
            last_progress = progress
            last_progress_ts = now
            lag_started_ts = None
        elif progress is not None:
            lag_started_ts = lag_started_ts or last_progress_ts

        kind = classify(data)
        lag_seconds = (now - lag_started_ts) if (kind == "scan_lag" and lag_started_ts) else 0

        is_failing = kind == "hard_hang" or kind == "busy_db" or (kind == "scan_lag" and lag_seconds >= SCAN_LAG_ALERT_SECONDS)

        # Per-poll diagnostic line, deliberately always-on rather than only-
        # on-failure: added 2026-07-25 after a real busy_db incident (33
        # genuine "Waited over 10 seconds for a busy database" errors in
        # Plex's own log) went completely undetected by this daemon with no
        # trace of why - control-panel's own access log confirmed this
        # process never once called a restart endpoint during that window.
        # Silent success and silent malfunction were indistinguishable from
        # outside the process; this line removes that ambiguity for next time.
        print(f"poll: state={data.get('state')} kind={kind} is_failing={is_failing} "
              f"busy_db={data.get('recent_busy_db_errors')} mount_ok={data.get('mount_ok')} "
              f"dstate={len(data.get('dstate_threads', []))} progress={progress} "
              f"lag={lag_seconds:.0f}s analysis_active={data.get('analysis_active')} "
              f"active_alert={active_alert}", file=sys.stderr)

        if is_failing and kind != active_alert:
            # kind != active_alert (not just "is None") - confirmed live
            # 2026-07-25: the old None-only check meant once any failure
            # kind was first alerted, active_alert got "stuck" on it and
            # never updated if the underlying problem changed mid-episode
            # (observed scan_lag -> busy_db transition where active_alert
            # stayed "scan_lag" for 12+ consecutive polls despite kind
            # correctly reading "busy_db" every time) - both the alert
            # message and the eventual "recovered from X" message would
            # describe the wrong, stale failure class.
            active_alert = kind
            if kind == "hard_hang":
                msg = (f"Plex FUSE/D-state hang detected ({len(data.get('dstate_threads', []))} D-state "
                       f"thread(s), mount_ok={data.get('mount_ok')}).")
            elif kind == "busy_db":
                msg = f"Plex SQLite lock contention detected ({data.get('recent_busy_db_errors')} recent 'busy database' errors)."
            else:
                msg = f"Plex scan progress stuck at {last_progress}% for {int(lag_seconds)}s."
            notify_discord(msg, "error" if kind == "hard_hang" else "warn")

        # hard_hang deliberately excluded - see the module docstring's Tier 2
        # note above. Only busy_db and sustained scan_lag still auto-restart
        # (Tier 1, a plain container restart carries no mount-cascade risk).
        should_restart = (
            is_failing
            and kind != "hard_hang"
            and (now - last_restart_ts) >= RESTART_COOLDOWN_SECONDS
            and (kind == "busy_db" or lag_seconds >= SCAN_LAG_RESTART_SECONDS)
        )
        if should_restart:
            last_restart_ts = now
            success, message = api_post("/api/container/plex/restart")
            notify_discord(f"Auto Tier 1 (plain restart) {'succeeded' if success else 'failed'}: {message}",
                            "warn" if success else "error")

        if not is_failing and active_alert is not None:
            notify_discord(f"Plex recovered from {active_alert.replace('_', ' ')}.", "info")
            active_alert = None
            lag_started_ts = None


if __name__ == "__main__":
    main()
