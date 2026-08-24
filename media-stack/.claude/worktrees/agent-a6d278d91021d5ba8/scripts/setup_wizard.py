#!/usr/bin/env python3
"""One-shot onboarding wizard for The Stack's .env file.

Run via the installer image's --setup mode (see entrypoint.sh):
    docker run --rm -p 8090:8090 -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest --setup

Serves a single HTML form built from .env.example (sections from
"# ---- X ----" headers, help text from comment lines above each KEY=
line), collects real values, and writes them to .env. Stdlib only - no
pip dependency, matching how lean the installer image already is.

Two-pass by design: RADARR_API_KEY/SONARR_API_KEY genuinely don't
exist until each arr app has booted once and generated its own key -
nothing external can supply them ahead of time. Re-running this same
wizard after first boot loads the just-written .env as defaults
(instead of .env.example's placeholders) so only the fields that
actually changed need retyping.
"""
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

# Can't be known before the corresponding app has booted once and
# generated its own key - see module docstring. PLEX_TOKEN fits the same
# shape: reading it (Settings -> a library item -> Get Info -> View XML)
# needs a running Plex with at least one library item, not just a running
# container - left unset it silently breaks every Control Panel Plex action.
POST_BOOT_KEYS = {
    "RADARR_API_KEY", "SONARR_API_KEY", "PLEX_TOKEN",
}

# Self-issued secrets with no external source - safe to generate for the
# user instead of asking them to run a command themselves. Empty since the
# torrent/debrid removal (was ZILEAN_POSTGRES_PASSWORD, ZILEAN_API_KEY) -
# kept as a named set rather than deleted so a future self-issued secret has
# an obvious place to go.
AUTO_GENERATE_KEYS: set[str] = set()

# Only these actually block `docker compose up` from working at all;
# everything else can legitimately stay "changeme" for now (optional
# Discord webhooks) or be filled in later (the post-boot arr keys).
REQUIRED_KEYS = {"PUID", "PGID", "TZ", "HOST_IP", "PLEX_URL"}

# Rendered as plain text inputs; everything else is password-masked.
PLAIN_TEXT_KEYS = REQUIRED_KEYS

FIELD_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
SECTION_RE = re.compile(r"^# ---- (.+?) ----$")


def parse_env_example(path: Path) -> list[dict]:
    sections = []
    current = None
    pending_help = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            pending_help = []
            continue
        m = SECTION_RE.match(line)
        if m:
            current = {"name": m.group(1), "fields": []}
            sections.append(current)
            pending_help = []
            continue
        if line.startswith("#"):
            pending_help.append(line.lstrip("#").strip())
            continue
        m = FIELD_RE.match(line)
        if m and current is not None:
            current["fields"].append(
                {"key": m.group(1), "default": m.group(2), "help": " ".join(pending_help)}
            )
            pending_help = []
    return sections


def parse_env_values(path: Path) -> dict:
    if not path.exists():
        return {}
    values = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def initial_value(key: str, default: str, existing: dict) -> str:
    if key in existing:
        return existing[key]
    if key in AUTO_GENERATE_KEYS and default == "changeme":
        return secrets.token_hex(16)
    return default


def render_form(sections: list[dict], existing: dict, is_rerun: bool) -> str:
    parts = []
    for section in sections:
        post_boot_fields = [f for f in section["fields"] if f["key"] in POST_BOOT_KEYS]
        normal_fields = [f for f in section["fields"] if f["key"] not in POST_BOOT_KEYS]
        if normal_fields:
            parts.append(f'<fieldset><legend>{escape(section["name"])}</legend>')
            for f in normal_fields:
                parts.append(render_field(f, existing))
            parts.append("</fieldset>")
        if post_boot_fields:
            parts.append(
                '<fieldset class="post-boot"><legend>⚠ Fill in after first boot</legend>'
                "<p>These don't exist yet on a fresh install - each app generates its own "
                "key the first time it starts. Bring the stack up first "
                "(<code>docker compose up -d</code>), open each app's "
                "<strong>Settings → General → Security → API Key</strong>, then re-run this "
                "wizard and paste them in here.</p>"
            )
            for f in post_boot_fields:
                parts.append(render_field(f, existing))
            parts.append("</fieldset>")
    banner = ""
    if is_rerun:
        banner = (
            '<p class="banner">Loaded your existing .env as defaults - only change what you '
            "need to; anything left blank keeps its current value.</p>"
        )
    return HTML_TEMPLATE.format(banner=banner, fields="\n".join(parts))


def render_field(f: dict, existing: dict) -> str:
    key, default, help_text = f["key"], f["default"], f["help"]
    value = initial_value(key, default, existing)
    input_type = "text" if key in PLAIN_TEXT_KEYS else "password"
    required = "required" if key in REQUIRED_KEYS else ""
    help_html = f'<span class="help">{escape(help_text)}</span>' if help_text else ""
    return (
        f'<label for="{key}">{key}{" *" if required else ""}</label>'
        f'<input type="{input_type}" id="{key}" name="{key}" value="{escape(value)}" '
        f'{required} autocomplete="off">'
        f"{help_html}"
    )


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def render_env_file(env_example_path: Path, submitted: dict, existing: dict) -> str:
    out_lines = []
    for raw_line in env_example_path.read_text().splitlines():
        m = FIELD_RE.match(raw_line.strip())
        if m:
            key, example_default = m.group(1), m.group(2)
            new_val = submitted.get(key, "").strip()
            if not new_val:
                new_val = existing.get(key, example_default)
            out_lines.append(f"{key}={new_val}")
        else:
            out_lines.append(raw_line)
    return "\n".join(out_lines) + "\n"


def write_env_atomic(target: Path, content: str) -> None:
    tmp = target.with_suffix(".env.tmp")
    tmp.write_text(content)
    os.replace(tmp, target)


HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>The Stack - Setup</title>
<style>
body {{ background:#111; color:#eee; font-family:system-ui,sans-serif; max-width:640px;
        margin:2rem auto; padding:0 1rem; }}
h1 {{ color:#e33; }}
fieldset {{ border:1px solid #333; border-radius:6px; margin-bottom:1.25rem; padding:1rem; }}
fieldset.post-boot {{ border-color:#a52; background:#1a1410; }}
legend {{ padding:0 .5rem; color:#e33; font-weight:600; }}
label {{ display:block; margin-top:.75rem; font-size:.9rem; color:#ccc; }}
input {{ width:100%; box-sizing:border-box; padding:.5rem; margin-top:.25rem; background:#1c1c1c;
         border:1px solid #444; border-radius:4px; color:#eee; }}
.help {{ display:block; font-size:.8rem; color:#888; margin-top:.2rem; }}
.banner {{ background:#132; border:1px solid #363; border-radius:6px; padding:.75rem; }}
button {{ background:#e33; color:#fff; border:0; border-radius:4px; padding:.75rem 1.5rem;
          font-size:1rem; cursor:pointer; margin-top:1rem; }}
button:hover {{ background:#c22; }}
</style></head>
<body>
<h1>The Stack - Setup</h1>
<p>Fields marked * are required for <code>docker compose up</code> to work at all.</p>
{banner}
<form method="post">
{fields}
<button type="submit">Write .env</button>
</form>
</body></html>
"""

SUCCESS_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>The Stack - Setup</title>
<style>body {{ background:#111; color:#eee; font-family:system-ui,sans-serif; max-width:640px;
margin:2rem auto; padding:0 1rem; }} code {{ background:#1c1c1c; padding:.15rem .4rem;
border-radius:3px; }} h1 {{ color:#3c3; }}</style></head>
<body>
<h1>.env written</h1>
<p>Next step:</p>
<pre><code>{next_step}</code></pre>
<p>You can close this window - the wizard has stopped.</p>
</body></html>
"""


def make_handler(target_dir: Path, env_example: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # avoid echoing form field names/values to stdout

        def do_GET(self):
            existing = parse_env_values(target_dir / ".env")
            sections = parse_env_example(env_example)
            body = render_form(sections, existing, is_rerun=bool(existing)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode()
            submitted = {k: v[0] for k, v in parse_qs(raw).items()}
            existing = parse_env_values(target_dir / ".env")
            had_arr_keys_before = any(existing.get(k, "changeme") != "changeme" for k in POST_BOOT_KEYS)

            content = render_env_file(env_example, submitted, existing)
            write_env_atomic(target_dir / ".env", content)

            now_has_arr_keys = any(
                submitted.get(k, existing.get(k, "changeme")) != "changeme" for k in POST_BOOT_KEYS
            )
            if now_has_arr_keys and not had_arr_keys_before:
                next_step = "docker compose up -d --force-recreate control-panel"
            else:
                next_step = "docker compose up -d"

            body = SUCCESS_TEMPLATE.format(next_step=next_step).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            print(f".env written to {target_dir / '.env'}")
            print(f"Next: {next_step}")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    return Handler


def main():
    if len(sys.argv) < 2:
        print("usage: setup_wizard.py <target_dir> [port]", file=sys.stderr)
        return 1
    target_dir = Path(sys.argv[1]).resolve()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8090

    env_example = target_dir / ".env.example"
    if not env_example.exists():
        print(f"{env_example} not found - scaffold the stack's files first.", file=sys.stderr)
        return 1

    httpd = HTTPServer(("0.0.0.0", port), make_handler(target_dir, env_example))
    print(f"Setup wizard listening on http://0.0.0.0:{port} - open it in a browser.")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
