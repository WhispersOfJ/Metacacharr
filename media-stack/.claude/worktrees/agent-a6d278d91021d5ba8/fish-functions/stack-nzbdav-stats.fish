# Usage: stack-nzbdav-stats
# Aggregate NzbDAV counts instead of the raw queue/history dumps
# stack-nzbdav-queue/stack-nzbdav-history already give.
function stack-nzbdav-stats --description 'Show aggregate NzbDAV queue/history stats'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/nzbdav/stats" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data.get('message', data))
"
end
