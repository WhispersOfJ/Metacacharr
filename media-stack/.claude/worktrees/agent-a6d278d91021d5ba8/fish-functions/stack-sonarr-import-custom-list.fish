# Usage: stack-sonarr-import-custom-list <base-url> <display-name> [--no-search]
# Adds a generic JSON/RSS feed as a Sonarr import list (CustomImport) -
# for any curated series list hosted as a URL, not covered by a dedicated
# implementation (Trakt/IMDb/Plex/Simkl).
function stack-sonarr-import-custom-list --description 'Add a generic JSON/RSS feed as a Sonarr import list'
    argparse 'no-search' -- $argv
    or return 1
    if test (count $argv) -ne 2
        echo "Usage: stack-sonarr-import-custom-list <base-url> <display-name> [--no-search]" >&2
        return 1
    end
    set -l search true
    set -q _flag_no_search; and set search false
    set -l body (python3 -c "
import json, sys
url, name, search = sys.argv[1:4]
print(json.dumps({'implementation':'CustomImport','name':name,'fields':{'baseUrl':url},'search_on_add':search=='true'}))
" "$argv[1]" "$argv[2]" "$search")
    __stack_api POST "/api/arr/sonarr/import-list/add" "$body"
end
