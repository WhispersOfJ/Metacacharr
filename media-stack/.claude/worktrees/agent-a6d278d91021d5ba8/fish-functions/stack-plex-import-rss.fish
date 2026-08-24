# Usage: stack-plex-import-rss <radarr|sonarr> <plex-watchlist-rss-url> [--no-search]
# Adds a Plex Watchlist RSS feed URL as an import list (PlexRssImport) -
# get the URL from https://app.plex.tv/desktop/#!/settings/watchlist.
# Distinct from stack-plex-import-watchlist: that one uses your account
# token directly (PlexImport), this one polls a public RSS feed instead.
function stack-plex-import-rss --description 'Add a Plex Watchlist RSS feed as a Radarr/Sonarr import list'
    argparse 'no-search' -- $argv
    or return 1
    if test (count $argv) -ne 2; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-plex-import-rss <radarr|sonarr> <plex-watchlist-rss-url> [--no-search]" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    set -l search true
    set -q _flag_no_search; and set search false
    set -l body (python3 -c "
import json, sys
print(json.dumps({'implementation':'PlexRssImport','name':'Plex Watchlist RSS','fields':{'url':sys.argv[1]},'search_on_add':sys.argv[2]=='true'}))
" "$argv[2]" "$search")
    __stack_api POST "/api/arr/$app/import-list/add" "$body"
end
