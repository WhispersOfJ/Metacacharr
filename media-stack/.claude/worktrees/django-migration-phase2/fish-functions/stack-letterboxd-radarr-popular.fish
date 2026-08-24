# Usage: stack-letterboxd-radarr-popular [--no-search] [--no-monitor] [--limit N] [--dry-run]
# Same technique as stack-letterboxd-radarr, applied to
# https://letterboxd.com/films/popular/.
#
# KNOWN LIMITATION: this page's poster grid is pure client-side JS
# hydration - confirmed live, the server-rendered HTML has zero film data
# at any header combination tried, unlike every other Letterboxd grid this
# technique covers. This command will currently always report "no films
# found." Left in place (rather than silently pointed at a different page)
# so the failure is honest instead of quietly returning the wrong list.
function stack-letterboxd-radarr-popular --description 'Add Letterboxd''s popular films to Radarr'
    argparse 'no-search' 'no-monitor' 'limit=' 'dry-run' -- $argv
    or return 1
    if test (count $argv) -ne 0
        echo "Usage: stack-letterboxd-radarr-popular [--no-search] [--no-monitor] [--limit N] [--dry-run]" >&2
        return 1
    end
    set -l url "https://letterboxd.com/films/popular/"
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
