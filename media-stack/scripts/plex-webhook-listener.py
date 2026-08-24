#!/usr/bin/env python3
"""Long-running listener for Plex's native webhooks (Plex Pass feature -
this account has it, confirmed via `myPlexSubscription` on the server's own
`/` endpoint). Posts a Discord embed with boxart the instant Plex fires
`library.new`, instead of waiting for plex-library-report.py's 30-minute
poll. Not configurable via this repo's own PLEX_TOKEN - webhooks are an
account-level Plex setting, added once by hand in the Plex web app under
Settings -> Webhooks -> Add Webhook, pointed at
`http://127.0.0.1:<PLEX_WEBHOOK_PORT>/plex-webhook` (see README).

Bound to 127.0.0.1 only: Plex runs with `network_mode: host`
(docker-compose.yml), so "localhost" from Plex's own perspective is this
same machine, and nothing else has a reason to reach this endpoint.

Plex's webhook POST is multipart/form-data with a `payload` JSON field and,
when the item's poster had already been matched/downloaded by the time the
event fired, a `thumb` file field with the image bytes already attached -
used directly when present. Falls back to fetching `Metadata.thumb` from
Plex's own API for the (usually rare) case where the item hadn't been
matched yet. Run by systemd/stack-plex-webhook.service - a long-running
listener, not a timer.

Posts are handed to a single background worker over a queue rather than
fired directly from the request thread: a season-pack import fires one
`library.new` per episode within seconds of each other, and posting that
many embeds concurrently would blow through Discord's per-webhook rate
limit (~5 requests/2s) and silently drop most of them. The worker paces
itself and retries once on an explicit 429 with the `Retry-After` Discord
sends back.
"""
import json
import mimetypes
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from email.parser import BytesParser
from email.policy import default as email_default_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent
DISCORD_GREEN = 0x57F287
SUMMARY_LIMIT = 300
MAX_POSTER_BYTES = 8 * 1024 * 1024
POST_PACING_SECONDS = 1.0


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
LISTEN_PORT = int(env_get("PLEX_WEBHOOK_PORT") or "9880")
METACACHE_URL = (env_get("METACACHE_URL") or "http://metacache:8765").rstrip("/")

post_queue = queue.Queue()


def plex_get_binary(path):
    sep = "&" if "?" in path else "?"
    url = f"{PLEX_URL}{path}{sep}X-Plex-Token={PLEX_TOKEN}"
    req = urllib.request.Request(url, headers={"Accept": "image/*"})
    with urllib.request.urlopen(req, timeout=15) as r:
        content_type = r.headers.get_content_type() or "image/jpeg"
        data = r.read(MAX_POSTER_BYTES + 1)
    if len(data) > MAX_POSTER_BYTES:
        return None, None
    return data, content_type


def build_multipart(payload, files):
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
        f"Content-Type: application/json\r\n\r\n{json.dumps(payload)}\r\n".encode()
    ]
    for field_name, filename, content_type, data in files:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
            + data
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", b"".join(parts)


def post_discord_once(embed, image):
    payload = {"embeds": [embed]}
    files = []
    if image:
        data, content_type = image
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        filename = f"poster{ext}"
        embed["image"] = {"url": f"attachment://{filename}"}
        files.append(("files[0]", filename, content_type, data))
    if files:
        content_type, body = build_multipart(payload, files)
    else:
        content_type, body = "application/json", json.dumps(payload).encode()
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": content_type, "User-Agent": "media-stack-plex-webhook/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30):
        pass


def post_discord(embed, image, label):
    try:
        post_discord_once(embed, image)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry_after = float(e.headers.get("Retry-After", "1"))
            print(f"rate-limited posting {label!r}, retrying after {retry_after}s", file=sys.stderr)
            time.sleep(retry_after)
            try:
                post_discord_once(embed, image)
            except Exception as e2:
                print(f"retry failed for {label!r}: {e2}", file=sys.stderr)
        else:
            print(f"discord post failed for {label!r}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"discord post failed for {label!r}: {e}", file=sys.stderr)


def worker():
    while True:
        embed, image, label = post_queue.get()
        if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "changeme":
            post_queue.task_done()
            continue
        post_discord(embed, image, label)
        print(f"posted: {label}", file=sys.stderr)
        post_queue.task_done()
        time.sleep(POST_PACING_SECONDS)


def parse_multipart(content_type_header, body):
    header = f"Content-Type: {content_type_header}\r\n\r\n".encode()
    msg = BytesParser(policy=email_default_policy).parsebytes(header + body)
    if not msg.is_multipart():
        return {}, None
    fields = {}
    thumb = None
    for part in msg.iter_parts():
        name = part.get_param("name", header="Content-Disposition")
        data = part.get_payload(decode=True)
        if part.get_filename():
            if name == "thumb" and data:
                thumb = (data, part.get_content_type())
        elif name:
            fields[name] = data
    return fields, thumb


def warm_metacache(payload):
    """Send the Plex webhook payload to Metacache for predictive warming."""
    if not METACACHE_URL:
        return
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{METACACHE_URL}/webhook/plex",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "media-stack-plex-webhook/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"metacache warm: {resp.status}", file=sys.stderr)
    except Exception as e:
        print(f"metacache warm failed: {e}", file=sys.stderr)


def handle_library_new(payload, attached_thumb):
    metadata = payload.get("Metadata", {})
    title = metadata.get("title", "Unknown")
    year = metadata.get("year")
    label = f"{title} ({year})" if year else title
    section = metadata.get("librarySectionTitle", "Library")
    grandparent = metadata.get("grandparentTitle")  # episode -> parent show title
    if grandparent and grandparent != title:
        label = f"{grandparent} — {label}"

    summary = metadata.get("summary", "")
    if len(summary) > SUMMARY_LIMIT:
        summary = summary[: SUMMARY_LIMIT - 1].rstrip() + "…"

    embed = {
        "title": label[:256],
        "color": DISCORD_GREEN,
        "footer": {"text": f"Added to {section}"},
    }
    if summary:
        embed["description"] = summary

    image = attached_thumb
    if not image and metadata.get("thumb") and PLEX_URL and PLEX_TOKEN:
        try:
            data, content_type = plex_get_binary(metadata["thumb"])
            if data:
                image = (data, content_type)
        except Exception as e:
            print(f"poster fetch failed for {label!r}: {e}", file=sys.stderr)

    post_queue.put((embed, image, label))

    # Trigger Metacache warm in background (non-blocking)
    threading.Thread(target=warm_metacache, args=(payload,), daemon=True).start()


class WebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", file=sys.stderr)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        # Ack immediately - Plex doesn't need to wait on Discord delivery,
        # and holding the connection open risks Plex's own webhook timeout.
        self.send_response(200)
        self.end_headers()

        content_type_header = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type_header:
            return
        try:
            fields, thumb = parse_multipart(content_type_header, body)
        except Exception as e:
            print(f"failed parsing webhook body: {e}", file=sys.stderr)
            return
        raw_payload = fields.get("payload")
        if not raw_payload:
            return
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return

        if payload.get("event") == "library.new":
            try:
                handle_library_new(payload, thumb)
            except Exception as e:
                print(f"failed handling library.new: {e}", file=sys.stderr)


def main():
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "changeme":
        print("DISCORD_WEBHOOK_URL not configured in .env - listener will run but drop everything", file=sys.stderr)
    threading.Thread(target=worker, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), WebhookHandler)
    print(f"listening on 127.0.0.1:{LISTEN_PORT} for Plex webhooks", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
