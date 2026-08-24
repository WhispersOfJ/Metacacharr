# Usage: stack-arr-recently-added <radarr|sonarr> [limit]
# What was added to management most recently, with file/episode counts -
# spot-checks whether a fresh add has actually been searched yet.
function stack-arr-recently-added --description 'List recently added items in Radarr/Sonarr with file status'
    if test (count $argv) -lt 1; or test (count $argv) -gt 2; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-arr-recently-added <radarr|sonarr> [limit]" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    set -l limit 10
    if test (count $argv) -eq 2
        set limit $argv[2]
    end
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/$app/recently-added?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    mon = 'monitored' if i.get('monitored') else 'unmonitored'
    if i.get('total_count') is not None:
        files = f\"{i.get('file_count') or 0}/{i['total_count']} files\"
    else:
        files = f\"{i.get('file_count') or 0} files\"
    print(f\"  {i['added']}  {i['title']:<40} {mon:<12} {files}\")
"
end
