# Usage: stack-radarr-import-list <list-url> <display-name> [--no-search]
# Adds a hosted Radarr-format list JSON as an import list
# (RadarrListImport) - community-curated lists published in that exact
# schema, distinct from stack-sonarr-import-custom-list's generic form.
function stack-radarr-import-list --description 'Add a hosted Radarr-list-format URL as a Radarr import list'
    argparse 'no-search' -- $argv
    or return 1
    if test (count $argv) -ne 2
        echo "Usage: stack-radarr-import-list <list-url> <display-name> [--no-search]" >&2
        return 1
    end
    set -l search true
    set -q _flag_no_search; and set search false
    set -l body (python3 -c "
import json, sys
url, name, search = sys.argv[1:4]
print(json.dumps({'implementation':'RadarrListImport','name':name,'fields':{'url':url},'search_on_add':search=='true'}))
" "$argv[1]" "$argv[2]" "$search")
    __stack_api POST "/api/arr/radarr/import-list/add" "$body"
end
