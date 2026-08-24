# Usage: stack-plex-sessions
# Who's watching what right now - direct play vs transcode, per session.
function stack-plex-sessions --description 'Show active Plex streaming sessions'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/plex/sessions" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for s in data.get('sessions', []):
    print(f\"  {s['user']:<15} {s['title']:<40} {s['decision']:<12} {s['progress_pct']}%  ({s['player']}, {s['state']})\")
"
end
