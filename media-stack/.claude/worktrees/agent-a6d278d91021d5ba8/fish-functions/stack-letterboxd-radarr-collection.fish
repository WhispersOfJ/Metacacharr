# Usage: stack-letterboxd-radarr-collection <letterboxd-collection-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]
# Same technique as stack-letterboxd-radarr, applied to a film collection
# (e.g. https://letterboxd.com/films/in/<collection-slug>/).
#
# KNOWN LIMITATION: /films/in/ is gated by an actual Cloudflare JS challenge
# on this path, not just header sniffing (confirmed live: a bare UA gets a
# real "Just a moment..." challenge page, not a plain 403). A full
# browser-shaped header set passes most of the time but not reliably - this
# command can intermittently fail with a fetch error that isn't this
# command's bug. Retry if it happens.
function stack-letterboxd-radarr-collection --description 'Add every film in a Letterboxd collection to Radarr'
    argparse 'no-search' 'no-monitor' 'limit=' 'dry-run' -- $argv
    or return 1
    if test (count $argv) -ne 1
        echo "Usage: stack-letterboxd-radarr-collection <letterboxd-collection-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]" >&2
        return 1
    end
    set -l url $argv[1]
    set -l search true
    set -l monitored true
    set -l limit 0
    set -l dry_run false
    set -l app radarr
    set -q _flag_no_search; and set search false
    set -q _flag_no_monitor; and set monitored false
    set -q _flag_limit; and set limit $_flag_limit
    set -q _flag_dry_run; and set dry_run true
    set -l body (python3 -c "
import json, sys
url, search, monitored, limit, dry_run, app = sys.argv[1:7]
payload = {'url': url, 'search': search == 'true', 'monitored': monitored == 'true', 'dry_run': dry_run == 'true', 'app': app}
if int(limit) > 0:
    payload['limit'] = int(limit)
print(json.dumps(payload))
" "$url" "$search" "$monitored" "$limit" "$dry_run" "$app")
    __stack_api POST "/api/arr/radarr/add-from-letterboxd-list" "$body"
end
