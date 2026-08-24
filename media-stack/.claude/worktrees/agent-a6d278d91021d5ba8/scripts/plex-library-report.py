#!/usr/bin/env python3
"""Diffs Plex's movie/show libraries against the last snapshot and posts
what was removed to Discord. Run every 30 minutes by
systemd/stack-plex-report.{service,timer}.

Only reports removals now - additions are reported instantly, with boxart,
by scripts/plex-webhook-listener.py reacting to Plex's own `library.new`
webhook (see README). Plex has no equivalent "item removed" webhook event,
so this periodic diff is still the only way to catch that; it used to cover
both directions before the webhook listener existed.

State lives in ~/.cache/plex-library-snapshot.json so the first run just
establishes a baseline instead of reporting every existing item as
"removed". Diffs on Plex's `guid` (stable across re-matches), not
`ratingKey` (which can get reassigned when an item is re-matched - confirmed
happening in this library during the WCW-PPV matching cleanup) so a
re-match doesn't show up as a false "removed X / added X" pair.
"""
import json
import sys
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

STACK_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = Path.home() / ".cache" / "plex-library-snapshot.json"
DISCORD_BLURPLE = 0x5865F2
DISCORD_ORANGE = 0xE67E22


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


PLEX_URL = (env_get("PLEX_URL") or "").rstrip("/")
PLEX_TOKEN = env_get("PLEX_TOKEN")
DISCORD_WEBHOOK_URL = env_get("DISCORD_WEBHOOK_URL")
HOST_LABEL = env_get("HOST_IP") or "Stack"


def plex_get(path):
    sep = "&" if "?" in path else "?"
    url = f"{PLEX_URL}{path}{sep}X-Plex-Token={PLEX_TOKEN}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_video_sections():
    data = plex_get("/library/sections")
    return [
        (d["key"], d["title"])
        for d in data["MediaContainer"].get("Directory", [])
        if d.get("type") in ("movie", "show")
    ]


def get_section_items(key):
    data = plex_get(f"/library/sections/{key}/all?X-Plex-Container-Size=100000")
    items = {}
    for m in data["MediaContainer"].get("Metadata", []):
        guid = m.get("guid") or f"ratingKey:{m['ratingKey']}"
        year = m.get("year", "")
        title = m.get("title", "Unknown")
        items[guid] = f"{title} ({year})" if year else title
    return items


def label_of(item):
    """Handles both this script's plain-string shape and the richer dict
    shape a brief v8.1.0 iteration wrote to snapshots, in case anyone's
    state file passed through that version before this reverted it."""
    return item if isinstance(item, str) else label_of(item.get("title", "Unknown"))


def load_previous():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_current(snapshot):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(snapshot))


def truncate_list(items, limit=20):
    items = sorted(items)
    shown = "\n".join(f"• {i}" for i in items[:limit])
    if len(items) > limit:
        shown += f"\n…and {len(items) - limit} more"
    return shown


def post_discord(embed):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "changeme":
        print("DISCORD_WEBHOOK_URL not configured, skipping notification", file=sys.stderr)
        return
    payload = json.dumps({"embeds": [embed]}).encode()
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        # Discord's edge (Cloudflare) 403s the default "Python-urllib/x.y"
        # User-Agent outright - any real UA string works.
        headers={"Content-Type": "application/json", "User-Agent": "media-stack-plex-report/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15):
        pass


def main():
    if not PLEX_URL or not PLEX_TOKEN:
        print("PLEX_URL/PLEX_TOKEN not configured in .env", file=sys.stderr)
        return 1

    sections = get_video_sections()
    previous = load_previous()
    is_baseline = not previous

    current = {}
    fields = []
    for key, title in sections:
        items = get_section_items(key)
        current[key] = {"title": title, "items": items}
        prev_items = previous.get(key, {}).get("items", {})

        if is_baseline:
            continue

        removed = [label_of(prev_items[g]) for g in prev_items if g not in items]
        if removed:
            fields.append({
                "name": f"➖ {title} — removed ({len(removed)})",
                "value": truncate_list(removed),
                "inline": False,
            })

    save_current(current)

    embed = {
        "title": "Plex Library Report",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": HOST_LABEL},
    }

    if is_baseline:
        total = sum(len(s["items"]) for s in current.values())
        embed["description"] = (
            f"Baseline established — tracking {total} items across "
            f"{len(sections)} librar{'y' if len(sections) == 1 else 'ies'}. "
            f"Future runs report anything removed since the last one "
            f"(additions are reported instantly by plex-webhook-listener.py)."
        )
        embed["color"] = DISCORD_BLURPLE
    elif not fields:
        embed["description"] = "No removals in the last 30 minutes."
        embed["color"] = DISCORD_BLURPLE
    else:
        embed["fields"] = fields[:25]  # Discord's hard cap on embed fields
        embed["color"] = DISCORD_ORANGE

    post_discord(embed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
