# Usage: stack-nzbdav-history [limit]  (default 20)
function stack-nzbdav-history --description 'Show NzbDAV''s recent download history (completed/failed)'
    set -l limit 20
    if test (count $argv) -ge 1
        set limit $argv[1]
    end
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/nzbdav/history?limit=$limit" | python3 -c "
import json, sys
items = json.load(sys.stdin)
if not items:
    print('No history yet.')
    sys.exit(0)
for it in items:
    line = f\"[{it['category']}] {it['name']}  {it['status']}  {it['size']}\"
    if it.get('fail_message'):
        line += f\"  - {it['fail_message']}\"
    print(line)
"
end
