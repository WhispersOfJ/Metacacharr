# Usage: stack-arr-list-implementations <radarr|sonarr>
# Every import-list type that app's own build supports (Simkl, TMDb
# Company/Keyword/User, Plex, Custom, etc), whether configured or not -
# discovery aid before using the *-import commands below.
function stack-arr-list-implementations --description 'List every import-list implementation Radarr/Sonarr supports'
    if test (count $argv) -ne 1; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-arr-list-implementations <radarr|sonarr>" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/$app/import-list/implementations" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['implementation']:<22} {i['name']}\")
"
end
