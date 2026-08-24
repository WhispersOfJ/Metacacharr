# Usage: stack-arr-import-candidates <radarr|sonarr>
# Lists files stuck in that app's queue that are ready to manually import,
# numbered for use with stack-arr-import.
function stack-arr-import-candidates --description 'List files ready to manually import in an *arr app'
    if test (count $argv) -ne 1; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-arr-import-candidates <radarr|sonarr>" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/$app/manual-import" | python3 -c "
import json, sys
items = json.load(sys.stdin)
if not items:
    print('No importable files right now - nothing stuck in the queue.')
    sys.exit(0)
for i, it in enumerate(items):
    label = it.get('episode') or it.get('match_title') or ''
    print(f\"[{i}] {it.get('name')}\")
    print(f\"     from: {it.get('queue_title')}  {label}  {it.get('quality')}  {it.get('size')}\")
    if it.get('rejections'):
        print(f\"     rejections: {', '.join(it['rejections'])}\")
print()
print('Run: stack-arr-import $argv[1] <index>')
"
end
