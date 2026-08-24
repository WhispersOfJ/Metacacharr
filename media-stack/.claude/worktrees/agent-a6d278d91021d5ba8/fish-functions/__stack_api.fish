# Private helper: call Control Panel's API (direct port, no Traefik/Authelia
# in front of it anymore) and print its `message` field. Works against both
# response shapes app.py returns: {"ok","message",...} on 2xx, and FastAPI's
# {"detail": {"ok","message",...}} wrapper on a raised HTTPException.
# Usage: __stack_api METHOD PATH [JSON_BODY]
# Exit status mirrors the API's own "ok" field (or the HTTP status if the
# body isn't JSON at all).
#
# Sends X-Api-Key from CONTROL_PANEL_SERVICE_API_KEY (media-stack/.env) on
# every call. app.py (still live as of Phase 3 of
# .claude/plans/evolved-control-panel-backend.plan.md) ignores unknown
# headers, so this is a no-op today - it's here so every stack-* command
# keeps working the moment the evolved backend (main.py, real auth) cuts
# over in Phase 5, instead of every one of them silently 401ing that day.
function __stack_api
    set -l method $argv[1]
    set -l path $argv[2]
    set -l body $argv[3]
    set -l host_ip 192.168.4.20
    # Hardcoded, not derived from the running file's location. Since Phase 8a
    # (2026-08-13) the stack-* functions ARE symlinks into this repo, but this
    # helper is not one of them - it has no stack- prefix, so
    # scripts/fish-functions-install.py does not manage it, and it stays a
    # plain copy. Keeping the path absolute means both arrangements resolve
    # to the same .env either way.
    set -l env_file /home/bear/Claude/media-stack/.env
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat "$env_file" 2>/dev/null))[2]
    set -l curl_opts -sS -X $method -w '\n%{http_code}'
    if test -n "$service_key"
        set curl_opts $curl_opts -H "X-Api-Key: $service_key"
    end
    if test -n "$body"
        set curl_opts $curl_opts -H 'Content-Type: application/json' -d $body
    end
    curl $curl_opts "http://$host_ip:8420$path" | python3 -c "
import json, sys
raw = sys.stdin.read()
body, _, code = raw.rpartition('\n')
try:
    data = json.loads(body) if body else {}
except ValueError:
    print(body or f'(empty response, HTTP {code})')
    sys.exit(1)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if isinstance(data, dict) and 'message' in data:
    print(data['message'])
    sys.exit(0 if data.get('ok') else 1)
print(json.dumps(data, indent=2))
sys.exit(0 if code.strip() == '200' else 1)
"
end
