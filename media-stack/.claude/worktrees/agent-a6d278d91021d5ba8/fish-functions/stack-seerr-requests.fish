# Usage: stack-seerr-requests [pending|approved|available|all]
# Media requests sitting in Seerr - confirms a request actually landed
# there before chasing why it's not showing up in Radarr/Sonarr.
function stack-seerr-requests --description 'List Seerr media requests by status'
    # Named req_status, not status - fish ties `status` to a real builtin
    # (the last command's exit code), same trap class as zsh's `path`
    # array; `set -l status ...` gets silently rejected and every later
    # $status read falls through to the builtin instead - confirmed live
    # (produced "filter=1" in the request URL, not "filter=pending").
    set -l req_status pending
    if test (count $argv) -eq 1
        set req_status $argv[1]
    end
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/seerr/requests?status=$req_status" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['createdAt']}  {i['title']:<40} {i['type']:<6} by {i['requestedBy']}  ({i['status']})\")
"
end
