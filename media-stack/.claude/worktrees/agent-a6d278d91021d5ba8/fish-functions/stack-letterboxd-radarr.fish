# Usage: stack-letterboxd-radarr <letterboxd-film-url> [--no-search] [--no-monitor] [--dry-run]
# Scrapes the film's TMDb id off its Letterboxd page (server-side, via
# Control Panel) and adds it to Radarr - no extra container needed, unlike
# screeny05/letterboxd-list-radarr's Redis-backed list adapter.
function stack-letterboxd-radarr --description 'Add a Letterboxd film to Radarr by URL'
    argparse 'no-search' 'no-monitor' 'dry-run' -- $argv
    or return 1
    if test (count $argv) -ne 1
        echo "Usage: stack-letterboxd-radarr <letterboxd-film-url> [--no-search] [--no-monitor] [--dry-run]" >&2
        return 1
    end
    set -l url $argv[1]
    set -l search true
    set -l monitored true
    set -l dry_run false
    set -l app radarr
    set -q _flag_no_search; and set search false
    set -q _flag_no_monitor; and set monitored false
    set -q _flag_dry_run; and set dry_run true
    set -l body (python3 -c "import json, sys; print(json.dumps({'url': sys.argv[1], 'search': sys.argv[2] == 'true', 'monitored': sys.argv[3] == 'true', 'dry_run': sys.argv[4] == 'true', 'app': sys.argv[5]}))" "$url" "$search" "$monitored" "$dry_run" "$app")
    __stack_api POST "/api/arr/radarr/add-from-letterboxd" "$body"
end
