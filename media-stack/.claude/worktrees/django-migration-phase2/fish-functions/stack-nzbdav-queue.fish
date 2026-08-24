function stack-nzbdav-queue --description 'Show NzbDAV''s current Usenet download queue'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/nzbdav/queue" | python3 -c "
import json, sys
items = json.load(sys.stdin)
if not items:
    print('Queue is empty.')
    sys.exit(0)
for it in items:
    left = f\" ({it['size_left_mb']}MB left)\" if it.get('status') == 'Downloading' else ''
    print(f\"[{it['category']}] {it['name']}  {it['status']} {it['percentage']}%{left}\")
"
end
