#!/usr/bin/env python3
"""Provision WatchState from a bare volume: add the Plex backend and register
the Plex webhook. Phase 6 of PLANS.md.

Headless, like other provisioning scripts in this batch. PLANS.md 6.2 assumed the Plex token
had to go in through a setup CLI or web onboarding; it does not. `POST
/v1/api/backends` takes everything, and there is no `backends:add` console
command anyway, so the API is the only scriptable path.

Three things the API demands that are not obvious from its error messages:

1. **`uuid` is required in practice, not optional.** WatchState sends the
   backend's uuid as Plex's `X-Plex-Client-Identifier` header. Omit it and the
   add fails with "X-Plex-Client-Identifier is missing" from a users-list call
   several layers down. Fetch it first from `/v1/api/backends/uuid/plex`.
2. **`user` is required too**, as the numeric Plex account id, and the same
   uuid has to be passed to the users-list call to get it. Without it the add
   fails with "Did not find matching user id '{id}'" - the literal
   placeholder, unsubstituted.
3. **The webhook URL must be the host IP, not `http://watchstate:8080`.**
   PLANS.md 6.4 assumed the docker-network address, but plex runs
   `network_mode: host` in this stack, so it cannot resolve the container
   name. It posts to `http://HOST_IP:8705/...`.

The webhook is registered into plex.tv from here (`POST
/v1/api/backend/plex/webhook`, which drives WatchState's own AddWebhook
action). No browser step.

The scheduled import stays enabled alongside the webhook - see WS_CRON_IMPORT
in docker-compose.yml for why that redundancy is deliberate.

Safe to re-run: an existing backend is reported and left alone rather than
recreated, since recreating it would issue a new webhook token and silently
orphan the one Plex already holds.

Usage:  python3 scripts/watchstate-provision.py [--dry-run]
"""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BASE = "http://localhost:8705"
API = f"{BASE}/v1/api"
TIMEOUT = 60
# WatchState names backends itself; this one is Plex, and the name is what the
# CLI and every /v1/api/backend/<name>/... route address it by.
BACKEND_NAME = "plex"
# Published port, not the container's 8080: plex is network_mode host and
# reaches WatchState the same way anything else on the LAN would.
WEBHOOK_PORT = 8705


def load_env() -> dict:
    env = {}
    for line in (REPO_ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def require(env: dict, key: str) -> str:
    value = env.get(key, "")
    if not value or value == "changeme":
        raise SystemExit(f"{key} is not set in .env - cannot provision.")
    return value


def request(method: str, path: str, api_key: str, body: dict | None = None):
    """Returns (http_status, parsed_json_or_none).

    Auth is the `X-apikey` header - WatchState also accepts `?apikey=` and a
    bearer token, but the header keeps the key out of its request log.
    """
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("X-apikey", api_key)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, None
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit(f"WatchState unreachable at {BASE}: {e}")


def error_message(body) -> str:
    """WatchState wraps failures as {"error": {"code": .., "message": ..}}."""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
    return str(body)


def existing_backend(api_key: str) -> dict | None:
    status, body = request("GET", "/backends", api_key)
    if status != 200:
        raise SystemExit(f"Could not list backends ({status}): {error_message(body)}")
    for backend in body or []:
        if backend.get("name") == BACKEND_NAME:
            return backend
    return None


def plex_uuid(env: dict, api_key: str) -> str:
    status, body = request("POST", "/backends/uuid/plex", api_key, {
        "url": require(env, "PLEX_URL"), "token": require(env, "PLEX_TOKEN"),
    })
    if status != 200 or not (body or {}).get("identifier"):
        raise SystemExit(f"  plex: could not read the server identifier ({status}): {error_message(body)}")
    return body["identifier"]


def admin_user_id(env: dict, api_key: str, uuid: str) -> int:
    """The Plex account id WatchState should track.

    The admin account, not simply the first one: this server also has a
    restricted 'guest' user, and tracking that one would record whatever the
    guest watched as Bear's own watch state.
    """
    status, body = request("POST", "/backends/users/plex", api_key, {
        "url": require(env, "PLEX_URL"), "token": require(env, "PLEX_TOKEN"), "uuid": uuid,
    })
    if status != 200 or not isinstance(body, list) or not body:
        raise SystemExit(f"  plex: could not list users ({status}): {error_message(body)}")
    admin = next((u for u in body if u.get("admin")), None)
    if admin is None:
        raise SystemExit(f"  plex: no admin user in {[u.get('name') for u in body]} - refusing to guess.")
    print(f"  plex: tracking user '{admin.get('name')}' (id {admin['id']}, admin)")
    return admin["id"]


def provision_backend(env: dict, api_key: str, dry_run: bool) -> dict:
    backend = existing_backend(api_key)
    if backend:
        # Left alone rather than recreated: a fresh add issues a new webhook
        # token, which would silently orphan the one Plex already posts to.
        print(f"  backend: '{BACKEND_NAME}' already exists ({backend.get('url')}), left as is")
        return backend
    if dry_run:
        print(f"  backend: would add '{BACKEND_NAME}' -> {env.get('PLEX_URL')} (import on, export off)")
        return {}

    uuid = plex_uuid(env, api_key)
    user = admin_user_id(env, api_key, uuid)
    status, body = request("POST", "/backends", api_key, {
        "type": "plex",
        "name": BACKEND_NAME,
        "url": require(env, "PLEX_URL"),
        "token": require(env, "PLEX_TOKEN"),
        "uuid": uuid,
        "user": user,
        "import": {"enabled": True},
        # Export writes watch state back INTO Plex. Plex is the only backend
        # here, so there is nothing to write back from, and an accidental
        # export is a mass write against Plex's SQLite DB.
        "export": {"enabled": False},
    })
    if status not in (200, 201):
        raise SystemExit(f"  backend: add failed ({status}): {error_message(body)}")
    print(f"  backend: added '{BACKEND_NAME}' -> {body.get('url')} (import on, export off)")
    return body


def provision_webhook(backend: dict, env: dict, api_key: str, dry_run: bool) -> None:
    """Point Plex at WatchState's webhook endpoint.

    The path comes back from the backend itself and carries that backend's own
    webhook token as `?apikey=` - one endpoint serves every backend type and
    the token is what identifies which one is posting, so it must not be
    hand-built or shared between backends.
    """
    path = ((backend.get("urls") or {}).get("webhook") or "").strip()
    if not path:
        raise SystemExit("  webhook: WatchState did not report a webhook URL for the backend.")
    url = f"http://{require(env, 'HOST_IP')}:{WEBHOOK_PORT}{path}"

    if dry_run:
        print(f"  webhook: would register http://{env.get('HOST_IP')}:{WEBHOOK_PORT}/v1/api/webhook?apikey=<token> with plex.tv")
        return

    status, body = request("POST", f"/backend/{BACKEND_NAME}/webhook", api_key, {"webhook_url": url})
    if status not in (200, 201):
        raise SystemExit(f"  webhook: registration failed ({status}): {error_message(body)}")
    # Deliberately not printing the URL - it carries the backend's webhook
    # token, and this script's output ends up in terminals and commit notes.
    print(f"  webhook: registered with plex.tv -> http://{env['HOST_IP']}:{WEBHOOK_PORT}/v1/api/webhook?apikey=<token>")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()

    env = load_env()
    api_key = require(env, "WS_API_KEY")

    status, version = request("GET", "/system/version", api_key)
    if status != 200:
        raise SystemExit(f"WatchState is not answering /system/version ({status}) - is the container up?")
    print(f"WatchState {(version or {}).get('version')} at {BASE}{' (dry run)' if args.dry_run else ''}")

    backend = provision_backend(env, api_key, args.dry_run)
    if backend:
        provision_webhook(backend, env, api_key, args.dry_run)
    print("Done." if not args.dry_run else "Dry run complete, nothing written.")


if __name__ == "__main__":
    main()
