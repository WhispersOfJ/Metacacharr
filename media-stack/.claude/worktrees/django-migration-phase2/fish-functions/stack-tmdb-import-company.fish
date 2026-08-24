# Usage: stack-tmdb-import-company <tmdb-company-id> <display-name> [--no-search]
# Adds a studio filmography as a Radarr import list (TMDbCompanyImport) -
# find the company id from a TMDB URL like themoviedb.org/company/2 (A24).
function stack-tmdb-import-company --description 'Add a TMDB studio filmography as a Radarr import list'
    argparse 'no-search' -- $argv
    or return 1
    if test (count $argv) -ne 2
        echo "Usage: stack-tmdb-import-company <tmdb-company-id> <display-name> [--no-search]" >&2
        return 1
    end
    set -l search true
    set -q _flag_no_search; and set search false
    set -l body (python3 -c "
import json, sys
company_id, name, search = sys.argv[1:4]
print(json.dumps({'implementation':'TMDbCompanyImport','name':name,'fields':{'companyId':company_id},'search_on_add':search=='true'}))
" "$argv[1]" "$argv[2]" "$search")
    __stack_api POST "/api/arr/radarr/import-list/add" "$body"
end
