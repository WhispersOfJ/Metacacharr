# Usage: stack-top [cpu|mem] [limit]
# Top containers by CPU or memory, compact - a quick "what's using
# resources right now" without scanning every card in the dashboard grid.
function stack-top --description 'Show top containers by CPU or memory usage'
    set -l by cpu
    set -l limit 10
    if test (count $argv) -ge 1
        set by $argv[1]
    end
    if test (count $argv) -ge 2
        set limit $argv[2]
    end
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/top?by=$by&limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['name']:<24} cpu={i['cpu_percent']:>6}%  mem={i['mem_percent']:>6}%  ({i['mem_used_mb']}MB)\")
"
end
