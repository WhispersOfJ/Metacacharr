# Usage: stack-command-queue-summary
# Backlog across every *arr app at once (radarr/sonarr/prowlarr) -
# the aggregate view of what stack-arr-backlog shows one app at a time.
function stack-command-queue-summary --description 'Show command queue backlog across all arr apps at once'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/command-queue-summary" | python3 -c "
import json, sys
raw = sys.stdin.read()
data = json.loads(raw)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for name, info in data.get('apps', {}).items():
    if 'error' in info:
        print(f'  {name:<10} error: {info[\"error\"]}')
    else:
        print(f\"  {name:<10} {info['total']:>4} total  {info['running']:>2} running  {info['queued']:>4} queued\")
"
end
