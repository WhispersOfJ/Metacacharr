# Usage: stack-tmdb-import-keyword <tmdb-keyword-id> <display-name> [--no-search]
# Adds a TMDB keyword-filtered list as a Radarr import list
# (TMDbKeywordImport) - e.g. keyword id 4565 is "time travel". Find ids
# via TMDB's own keyword search (no public numeric lookup UI - easiest
# path is a movie page's Keywords section, which links the id).
function stack-tmdb-import-keyword --description 'Add a TMDB keyword-filtered list as a Radarr import list'
    argparse 'no-search' -- $argv
    or return 1
    if test (count $argv) -ne 2
        echo "Usage: stack-tmdb-import-keyword <tmdb-keyword-id> <display-name> [--no-search]" >&2
        return 1
    end
    set -l search true
    set -q _flag_no_search; and set search false
    set -l body (python3 -c "
import json, sys
keyword_id, name, search = sys.argv[1:4]
print(json.dumps({'implementation':'TMDbKeywordImport','name':name,'fields':{'keywordId':keyword_id},'search_on_add':search=='true'}))
" "$argv[1]" "$argv[2]" "$search")
    __stack_api POST "/api/arr/radarr/import-list/add" "$body"
end
