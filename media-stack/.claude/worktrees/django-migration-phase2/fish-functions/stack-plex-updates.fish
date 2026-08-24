# Usage: stack-plex-updates
# Checks whether Plex has found a newer release on its current update
# channel - a check only, this stack pins Plex deliberately (see README's
# Image pinning policy) rather than auto-applying anything.
function stack-plex-updates --description 'Check for a Plex update (check only, does not apply it)'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/plex/updates" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, dict) and isinstance(d.get('detail'), dict):
    d = d['detail']
print(f\"Running: {d.get('running_version')}\")
if d.get('update_available'):
    print('Update available:')
    for r in d.get('releases', []):
        print(f\"  {r.get('version')}  (added {r.get('added_at')})\")
else:
    print('No update available on the current channel.')
"
end
