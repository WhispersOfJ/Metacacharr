# Usage: stack-letterboxd-radarr-list <letterboxd-list-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]
#        [--tags-as-radarr-tags] [--sonarr-crossover] [--rating-quality-map rating:profile,rating:profile,...]
# Same technique as stack-letterboxd-radarr, applied to a whole custom list
# (e.g. https://letterboxd.com/<user>/list/<slug>/): scrapes every film's
# slug off the list's paginated grid (max 10 pages / 720 films), then each
# film's own page for its TMDb id, and adds whatever isn't already in
# Radarr. Server-side via Control Panel - no extra container needed.
# --tags-as-radarr-tags: scrapes the page owner's Letterboxd tags per film
#   and attaches them as Radarr tags on add.
# --sonarr-crossover: for any film Letterboxd carries with no TMDb movie
#   match, checks Sonarr's own series-lookup-by-title and adds it there
#   instead if it's actually a miniseries/TV special.
# --rating-quality-map: only meaningful on the page owner's own
#   /films/ or /watchlist/ URL (where ratings are visible) - maps the
#   owner's 1-10 Letterboxd star rating to a Radarr quality-profile name,
#   e.g. --rating-quality-map 10:Remux-1080p,2:HD-1080p
function stack-letterboxd-radarr-list --description 'Add every film in a Letterboxd list to Radarr'
    argparse 'no-search' 'no-monitor' 'limit=' 'dry-run' 'tags-as-radarr-tags' 'sonarr-crossover' 'rating-quality-map=' -- $argv
    or return 1
    if test (count $argv) -ne 1
        echo "Usage: stack-letterboxd-radarr-list <letterboxd-list-url> [--no-search] [--no-monitor] [--limit N] [--dry-run] [--tags-as-radarr-tags] [--sonarr-crossover] [--rating-quality-map rating:profile,...]" >&2
        return 1
    end
    set -l url $argv[1]
    set -l search true
    set -l monitored true
    set -l limit 0
    set -l dry_run false
    set -l tags_as_radarr_tags false
    set -l sonarr_crossover false
    set -l rating_map ""
    set -l app radarr
    set -l sonarr_app sonarr
    set -q _flag_no_search; and set search false
    set -q _flag_no_monitor; and set monitored false
    set -q _flag_limit; and set limit $_flag_limit
    set -q _flag_dry_run; and set dry_run true
    set -q _flag_tags_as_radarr_tags; and set tags_as_radarr_tags true
    set -q _flag_sonarr_crossover; and set sonarr_crossover true
    set -q _flag_rating_quality_map; and set rating_map $_flag_rating_quality_map
    set -l body (python3 -c "
import json, sys
url, search, monitored, limit, dry_run, tags, crossover, rating_map, app, sonarr_app = sys.argv[1:11]
payload = {
    'url': url, 'search': search == 'true', 'monitored': monitored == 'true', 'dry_run': dry_run == 'true',
    'tags_as_radarr_tags': tags == 'true', 'sonarr_crossover': crossover == 'true', 'app': app, 'sonarr_app': sonarr_app,
}
if int(limit) > 0:
    payload['limit'] = int(limit)
if rating_map:
    pairs = [p.split(':', 1) for p in rating_map.split(',') if ':' in p]
    payload['rating_quality_map'] = {k: v for k, v in pairs}
print(json.dumps(payload))
" "$url" "$search" "$monitored" "$limit" "$dry_run" "$tags_as_radarr_tags" "$sonarr_crossover" "$rating_map" "$app" "$sonarr_app")
    __stack_api POST "/api/arr/radarr/add-from-letterboxd-list" "$body"
end
