# Usage: stack-prowlarr-indexers
# Every configured Prowlarr indexer's enabled/priority state.
function stack-prowlarr-indexers --description 'List Prowlarr indexers with enabled state and priority'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/prowlarr/indexers" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    mark = 'on ' if i['enabled'] else 'off'
    print(f\"  [{mark}] pri={i['priority']:<3} {i['name']}\")
"
end
