# Usage: stack-mdblist-import <mdblist-list-url> [--no-search] [--no-monitor] [--dry-run] [--limit N]
# Imports an MDBList list, routing movies to Radarr and TV shows to Sonarr
# in one call (server-side, via Control Panel). Works on any public
# MDBList list, including their own mirrors of common IMDb lists (e.g.
# search mdblist.com for "imdb top 250") - direct IMDb list import isn't
# possible, IMDb's list pages sit behind a Cloudflare-class bot challenge.
function stack-mdblist-import --description 'Import an MDBList list into Radarr and Sonarr'
    argparse 'no-search' 'no-monitor' 'dry-run' 'limit=' -- $argv
    or return 1
    if test (count $argv) -ne 1
        echo "Usage: stack-mdblist-import <mdblist-list-url> [--no-search] [--no-monitor] [--dry-run] [--limit N]" >&2
        return 1
    end
    set -l url $argv[1]
    set -l search true
    set -l monitored true
    set -l dry_run false
    set -l limit 0
    set -l app radarr
    set -l sonarr_app sonarr
    set -q _flag_no_search; and set search false
    set -q _flag_no_monitor; and set monitored false
    set -q _flag_dry_run; and set dry_run true
    set -q _flag_limit; and set limit $_flag_limit
    set -l body (python3 -c "
import json, sys
url, search, monitored, dry_run, limit, app, sonarr_app = sys.argv[1:8]
payload = {'list_url': url, 'search': search == 'true', 'monitored': monitored == 'true', 'dry_run': dry_run == 'true', 'app': app, 'sonarr_app': sonarr_app}
if int(limit) > 0:
    payload['limit'] = int(limit)
print(json.dumps(payload))
" "$url" "$search" "$monitored" "$dry_run" "$limit" "$app" "$sonarr_app")
    __stack_api POST "/api/mdblist/import-list" "$body"
end
