# Usage: stack-arr-queue-errors
# Only queue items an arr app has already flagged as a problem itself -
# quick triage across radarr/sonarr instead of scanning each
# app's own full queue grid by eye.
function stack-arr-queue-errors --description 'Show only errored/warning queue items across all arr apps'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/queue-errors" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for app_name, items in data.get('apps', {}).items():
    if isinstance(items, dict) and 'error' in items:
        print(f'  {app_name}: lookup failed')
        continue
    for i in items:
        msgs = '; '.join(i.get('messages') or [])
        print(f\"  [{app_name}] {i['status']:<10} {i['title']}  {msgs}\")
"
end
