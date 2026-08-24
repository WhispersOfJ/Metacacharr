function stack-queue-status --description 'Show every app''s download queue with a live-measured speed and ETA'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    echo 'Measuring (2 samples, ~4s apart - each app''s own timeleft/progress reporting is unreliable in this stack)...' >&2
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/queue-status" | python3 -c "
import json, sys

data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if not data.get('ok', True):
    print(data.get('message', 'Request failed.'))
    sys.exit(1)

print(data['message'])

order = ['radarr', 'sonarr', 'nzbdav', 'plex']
queues = data.get('queues', {})

def line(item):
    bits = [item['title']]
    if item.get('speed'):
        bits.append(f\"{item['speed']}\")
    if item.get('size_left'):
        bits.append(f\"{item['size_left']} left\")
    if item.get('progress'):
        bits.append(f\"{item['progress']}\")
    if item.get('eta'):
        bits.append(f\"ETA {item['eta']}\")
    if item.get('note'):
        bits.append(f\"({item['note']})\")
    return '  '.join(bits)

for name in order:
    q = queues.get(name)
    if q is None:
        continue
    print()
    print(f\"{q['label']}:\", end=' ')
    if q.get('error'):
        print(f\"{q['error']}\")
        continue
    if not q['total']:
        print('empty')
        continue
    print(f\"{q['total']} item(s)\")
    for bucket in ('downloading', 'stalled', 'queued', 'importing'):
        items = q.get(bucket) or []
        if not items:
            continue
        print(f\"  {bucket}:\")
        for it in items:
            print(f\"    {line(it)}\")

print()
print('Totals:')
for name in order:
    q = queues.get(name)
    if q is None:
        continue
    if q.get('error'):
        print(f\"  {q['label']}: {q['error']}\")
    else:
        print(f\"  {q['label']}: {q['total']}\")
"
end
