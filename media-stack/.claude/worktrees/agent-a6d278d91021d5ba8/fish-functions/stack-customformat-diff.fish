# Usage: stack-customformat-diff <radarr|sonarr>
# Diffs the current custom-format scores against the last time this ran,
# then updates the cache - neither app has a native change log for
# format-score edits made through the API, so this is the only way to
# see what actually changed since the last check.
function stack-customformat-diff --description 'Diff current Radarr/Sonarr custom-format scores against the last check'
    if test (count $argv) -ne 1; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-customformat-diff <radarr|sonarr>" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    set -l cache_dir "$HOME/.cache/stack-cli"
    mkdir -p "$cache_dir"
    set -l cache_file "$cache_dir/customformat-$app.json"
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    set -l current (curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/$app/customformat-snapshot")
    python3 -c "
import json, sys, os

raw = sys.argv[1]
cache_file = sys.argv[2]
data = json.loads(raw)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if not data.get('ok', True) and 'profiles' not in data:
    print(data.get('message', 'request failed'))
    sys.exit(1)
print(data['message'])

profiles = data['profiles']
old = {}
if os.path.isfile(cache_file):
    with open(cache_file) as f:
        old = json.load(f)

any_diff = False
for profile_name, formats in profiles.items():
    old_formats = old.get(profile_name, {})
    all_names = sorted(set(formats) | set(old_formats))
    for name in all_names:
        new_score = formats.get(name)
        old_score = old_formats.get(name)
        if new_score != old_score:
            any_diff = True
            if old_score is None:
                print(f'  [{profile_name}] + {name}: {new_score}')
            elif new_score is None:
                print(f'  [{profile_name}] - {name} (was {old_score})')
            else:
                print(f'  [{profile_name}] ~ {name}: {old_score} -> {new_score}')

if not any_diff:
    print('  No changes since last check.' if old else '  First check - nothing to diff against yet.')

with open(cache_file, 'w') as f:
    json.dump(profiles, f)
" "$current" "$cache_file"
end
