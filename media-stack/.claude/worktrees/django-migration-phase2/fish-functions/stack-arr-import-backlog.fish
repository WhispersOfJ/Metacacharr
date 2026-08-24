# Usage: stack-arr-import-backlog
# Only the items sitting on "waiting on import" (NzbDAV already fetched
# them, radarr/sonarr just haven't imported yet) - the wall of per-episode
# lines stack-queue-status prints for a full-series grab (e.g. House
# S01-S08 landing at once) collapses here into one grouped count per
# release, so the actual import backlog is readable at a glance.
function stack-arr-import-backlog --description 'Show only items waiting on import across radarr/sonarr, grouped by release'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/queue-status" | python3 -c "
import json, sys
from collections import Counter

data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if not data.get('ok', True):
    print(data.get('message', 'Request failed.'))
    sys.exit(1)

order = ['radarr', 'sonarr']
queues = data.get('queues', {})
grand_total = 0

for name in order:
    q = queues.get(name)
    if q is None:
        continue
    if q.get('error'):
        print(f\"{q['label']}: {q['error']}\")
        continue
    items = q.get('importing') or []
    if not items:
        print(f\"{q['label']}: nothing waiting on import\")
        continue
    counts = Counter(it['title'] for it in items)
    print(f\"{q['label']}: {len(items)} item(s) waiting on import ({len(counts)} distinct release(s))\")
    for title, n in counts.most_common():
        suffix = f'  x{n}' if n > 1 else ''
        print(f'  {title}{suffix}')
    grand_total += len(items)
    print()

print(f'Total waiting on import: {grand_total}')
"
end
