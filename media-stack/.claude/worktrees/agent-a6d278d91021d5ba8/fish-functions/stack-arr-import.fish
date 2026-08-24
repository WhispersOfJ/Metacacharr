# Usage: stack-arr-import <radarr|sonarr> <index>
# Re-fetches the candidate list fresh (the queue can change between listing
# and importing) and imports the one at <index> - see
# stack-arr-import-candidates for the numbered list.
function stack-arr-import --description 'Import a file listed by stack-arr-import-candidates'
    if test (count $argv) -ne 2; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-arr-import <radarr|sonarr> <index>" >&2
        return 1
    end
    set -l host_ip 192.168.4.20
    set -l app (__stack_arr_app $argv[1])
    set -l body (curl -sS "http://$host_ip:8420/api/arr/$app/manual-import" | python3 -c "
import json, sys
items = json.load(sys.stdin)
idx = int(sys.argv[1])
if idx < 0 or idx >= len(items):
    print(f'No candidate at index {idx} ({len(items)} available) - run stack-arr-import-candidates $app again.', file=sys.stderr)
    sys.exit(1)
print(json.dumps(items[idx]['file']))
" $argv[2])
    if test -z "$body"
        return 1
    end
    __stack_api POST "/api/arr/$app/manual-import" $body
end
