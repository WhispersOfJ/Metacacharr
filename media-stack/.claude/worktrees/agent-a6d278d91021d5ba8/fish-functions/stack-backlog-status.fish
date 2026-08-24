function stack-backlog-status --description 'Show every app''s wanted/missing backlog with a throughput-projected ETA'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/backlog-status" | python3 -c "
import json, sys

data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if not data.get('ok', True):
    print(data.get('message', 'Request failed.'))
    sys.exit(1)

print(data['message'])
print()

order = ['radarr', 'sonarr']
apps = data.get('apps', {})
for name in order:
    a = apps.get(name)
    if a is None:
        continue
    if a.get('error'):
        print(f\"{a['label']:<10} {a['error']}\")
        continue
    rate = f\"{a['rate_per_hour']}/hr\" if a['rate_per_hour'] else 'no recent pace'
    print(f\"{a['label']:<10} {a['missing']:>6} missing   {rate:<16} ETA {a['eta']}\")
"
end
