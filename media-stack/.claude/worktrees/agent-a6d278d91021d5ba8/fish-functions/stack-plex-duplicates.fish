# Usage: stack-plex-duplicates [min_gb]
# Movies carrying redundant duplicate copies (combined size well beyond a
# single real multi-version upgrade) - the exact check that found ~700GB
# of redundant Halloween 4/5 and Elm Street 4 releases in one session.
function stack-plex-duplicates --description 'Flag Plex movies carrying redundant duplicate files'
    set -l min_gb 5.0
    if test (count $argv) -eq 1
        set min_gb $argv[1]
    end
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/plex/duplicates?min_gb=$min_gb" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['title']} ({i['year']})  {i['file_count']} files  {i['total_gb']}GB total (largest {i['largest_gb']}GB)  ratingKey={i['ratingKey']}\")
"
end
