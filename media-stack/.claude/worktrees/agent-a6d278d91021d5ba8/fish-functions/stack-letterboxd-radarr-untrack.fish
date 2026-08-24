# Usage: stack-letterboxd-radarr-untrack <letterboxd-list-url>
function stack-letterboxd-radarr-untrack --description 'Stop nightly-syncing a tracked Letterboxd list'
    if test (count $argv) -ne 1
        echo "Usage: stack-letterboxd-radarr-untrack <letterboxd-list-url>" >&2
        return 1
    end
    set -l body (python3 -c "import json, sys; print(json.dumps({'url': sys.argv[1]}))" "$argv[1]")
    __stack_api POST "/api/arr/letterboxd/untrack" "$body"
end
