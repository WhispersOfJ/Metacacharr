# Usage: stack-arr-import-starvation
# Answers "why is nothing showing up in Sonarr/Radarr" when the queue looks
# empty and healthy. RefreshMonitoredDownloads both polls the download client
# and triggers imports, so when a bulk search backlog starves it out of the
# command pool the queue reports ZERO items and every ordinary queue check
# reads clean while imports are fully stopped. Read-only: the matching
# auto-remediation runs inside stack-queue-autofix's 5-minute loop.
function stack-arr-import-starvation --description 'Detect Radarr/Sonarr imports starved by a search backlog'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/import-starvation" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for app_name, v in data.get('apps', {}).items():
    if v.get('starved'):
        state = 'STARVED'
    elif v.get('lagging'):
        state = 'LAGGING'
    else:
        state = 'ok'
    print(f\"  [{state:<7}] {v['label']}\")
    print(f\"      refresh queued {v['starved_seconds']}s behind {v['queued_searches']} search(es), {v['active_commands']} active command(s)\")
    print(f\"      last grab {v['last_grab']}  last import {v['last_import']}  lag {v['lag_seconds']}s\")
    if state != 'ok':
        print(f'      {v[\"reason\"]}')
"
end
