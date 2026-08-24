function stack-disk-config-sizes --description 'Per-app config/ directory size, largest first'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/disk-usage" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, dict) and isinstance(d.get('detail'), dict):
    d = d['detail']
for s in d.get('sizes', []):
    mb = s['mb']
    size = f'{mb/1024:.1f} GB' if mb >= 1024 else f'{mb:.1f} MB'
    print(f\"{s['app']:<24} {size}\")
"
end
