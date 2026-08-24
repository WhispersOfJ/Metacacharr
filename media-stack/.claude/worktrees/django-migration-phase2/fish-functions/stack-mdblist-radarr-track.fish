# Usage: stack-mdblist-radarr-track <mdblist-list-url> [--label TEXT]
# Registers an MDBList list for the nightly diff-only sync
# (mirrors stack-letterboxd-radarr-track). Adding, then never untracking,
# is how a list stays synced indefinitely - untrack with
# stack-mdblist-radarr-untrack when done.
function stack-mdblist-radarr-track --description 'Register an MDBList list for nightly diff-only sync'
    argparse 'label=' -- $argv
    or return 1
    if test (count $argv) -ne 1
        echo "Usage: stack-mdblist-radarr-track <mdblist-list-url> [--label TEXT]" >&2
        return 1
    end
    set -l url $argv[1]
    set -l label ""
    set -l app radarr
    set -l sonarr_app sonarr
    set -q _flag_label; and set label $_flag_label
    set -l body (python3 -c "
import json, sys
url, label, app, sonarr_app = sys.argv[1:5]
payload = {'url': url, 'app': app, 'sonarr_app': sonarr_app}
if label:
    payload['label'] = label
print(json.dumps(payload))
" "$url" "$label" "$app" "$sonarr_app")
    __stack_api POST "/api/mdblist/track" "$body"
end
