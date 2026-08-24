# Usage: stack-plex-empty-trash [library name ...]
# No args = every library. With args = just that one (case-insensitive
# match against its Plex title, e.g. "TV Shows").
function stack-plex-empty-trash --description 'Empty trash on one Plex library, or all of them'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    if test (count $argv) -eq 0
        curl -sS -H "X-Api-Key: $service_key" -X POST "http://$host_ip:8420/api/plex/empty-trash" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, dict) and isinstance(d.get('detail'), dict):
    d = d['detail']
print(d.get('message', d))
sys.exit(0 if d.get('ok', True) else 1)
"
        return
    end
    set -l library (string join ' ' $argv)
    set -l encoded (python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" $library)
    curl -sS -H "X-Api-Key: $service_key" -X POST "http://$host_ip:8420/api/plex/empty-trash?library=$encoded" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, dict) and isinstance(d.get('detail'), dict):
    d = d['detail']
print(d.get('message', d))
sys.exit(0 if d.get('ok', True) else 1)
"
end
