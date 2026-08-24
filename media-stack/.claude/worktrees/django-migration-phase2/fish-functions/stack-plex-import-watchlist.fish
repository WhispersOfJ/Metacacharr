# Usage: stack-plex-import-watchlist <radarr|sonarr> [--no-search]
# Adds your own Plex watchlist as a native import list (PlexImport) - one
# call each for movies (Radarr) or TV (Sonarr). Requires Plex's own OAuth
# token to already be set up in that app (same as any other Plex-backed
# import list) - this only creates the list entry, not the Plex auth link.
function stack-plex-import-watchlist --description 'Add your Plex watchlist as a Radarr/Sonarr import list'
    argparse 'no-search' -- $argv
    or return 1
    if test (count $argv) -ne 1; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-plex-import-watchlist <radarr|sonarr> [--no-search]" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    set -l search true
    set -q _flag_no_search; and set search false
    set -l body '{"implementation":"PlexImport","name":"Plex Watchlist","fields":{},"search_on_add":'"$search"'}'
    __stack_api POST "/api/arr/$app/import-list/add" "$body"
end
