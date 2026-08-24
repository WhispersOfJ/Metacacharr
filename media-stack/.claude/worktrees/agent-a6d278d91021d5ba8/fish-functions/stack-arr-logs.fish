# Usage: stack-arr-logs <radarr|sonarr|prowlarr> [lines]
# Takes a *container* name, not an ARR_APPS key - this route reads Docker
# logs, so prowlarr is valid here alongside the two Arr instances.
function stack-arr-logs --description 'Tail an *arr app''s container log directly'
    if test (count $argv) -lt 1
        echo "Usage: stack-arr-logs <radarr|sonarr|prowlarr> [lines]" >&2
        return 1
    end
    set -l container $argv[1]
    if test $argv[1] != prowlarr
        set container (__stack_arr_app --container $argv[1])
        or begin
            echo "Unknown app '$argv[1]' - use radarr, sonarr, or prowlarr." >&2
            return 1
        end
    end
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    set -l lines 100
    if test (count $argv) -ge 2
        set lines $argv[2]
    end
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/$container/logs?lines=$lines" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, dict) and isinstance(d.get('detail'), dict):
    d = d['detail']
if not d.get('ok', True):
    print(d.get('message', 'error'), file=sys.stderr)
    sys.exit(1)
print(d.get('log', ''))
"
end
