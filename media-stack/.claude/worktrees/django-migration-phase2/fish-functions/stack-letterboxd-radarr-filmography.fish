# Usage: stack-letterboxd-radarr-filmography <role> <slug> [--no-search] [--no-monitor] [--limit N] [--dry-run]
# role is a Letterboxd crew-role URL segment: actor, director, writer,
# producer, editor, cinematography, composer, etc. Builds
# https://letterboxd.com/<role>/<slug>/ and applies the same technique as
# stack-letterboxd-radarr: scrapes every film's slug off the paginated grid
# (max 10 pages / 720 films), then each film's own page for its TMDb id, and
# adds whatever isn't already in Radarr. An unrecognized role just 404s with
# a clear error - roles aren't hardcoded here.
function stack-letterboxd-radarr-filmography --description 'Add every film in a Letterboxd person''s filmography to Radarr'
    argparse 'no-search' 'no-monitor' 'limit=' 'dry-run' -- $argv
    or return 1
    if test (count $argv) -ne 2
        echo "Usage: stack-letterboxd-radarr-filmography <role> <slug> [--no-search] [--no-monitor] [--limit N] [--dry-run]" >&2
        echo "  role examples: actor, director, writer, producer, editor, cinematography, composer" >&2
        return 1
    end
    set -l role $argv[1]
    set -l slug $argv[2]
    set -l url "https://letterboxd.com/$role/$slug/"
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
