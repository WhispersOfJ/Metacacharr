# Usage: stack-plex-recently-added [limit]
# What actually finished importing and became visible in Plex, across
# every movie/show library - complements stack-arr-recently-added (which shows
# what was added *to management*, not necessarily downloaded yet).
function stack-plex-recently-added --description 'Show recently added items visible in Plex'
    set -l limit 15
    if test (count $argv) -eq 1
        set limit $argv[1]
    end
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/plex/recently-added?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['title']} ({i['year']})  [{i['librarySectionTitle']}]\")
"
end
