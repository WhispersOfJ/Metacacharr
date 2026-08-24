# Usage: stack-mdblist-radarr-untrack <mdblist-list-url>
function stack-mdblist-radarr-untrack --description 'Stop nightly-syncing a tracked MDBList list'
    if test (count $argv) -ne 1
        echo "Usage: stack-mdblist-radarr-untrack <mdblist-list-url>" >&2
        return 1
    end
    set -l body (python3 -c "import json, sys; print(json.dumps({'url': sys.argv[1]}))" "$argv[1]")
    __stack_api POST "/api/mdblist/untrack" "$body"
end
