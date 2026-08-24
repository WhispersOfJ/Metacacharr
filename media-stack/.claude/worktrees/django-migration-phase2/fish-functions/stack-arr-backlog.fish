function stack-arr-backlog --description 'Show an arr app''s internal command queue backlog (searches, RSS sync, bulk moves, etc)'
    if test (count $argv) -ne 1; or not __stack_arr_app $argv[1] >/dev/null
        echo 'Usage: stack-arr-backlog <radarr|sonarr>' >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/$app/command-backlog" | python3 -c "
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except ValueError:
    print(raw)
    sys.exit(1)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if not data.get('ok', True):
    print(data.get('message', raw))
    sys.exit(1)

print(data['message'])

running = data.get('running') or []
if running:
    print()
    print('Currently running:')
    for c in running:
        print(f\"  {c['id']:>6}  {c['name']:<28} started {c['started']}\")

oldest = data.get('oldest_queued') or []
if oldest:
    print()
    print(f\"Oldest queued (of {data.get('queued_total', len(oldest))} total):\")
    for c in oldest:
        print(f\"  {c['id']:>6}  {c['name']:<28} queued  {c['queued']}\")
"
end
