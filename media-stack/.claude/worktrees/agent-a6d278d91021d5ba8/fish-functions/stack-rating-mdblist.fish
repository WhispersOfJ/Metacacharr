# Usage: stack-rating-mdblist <imdb-id>
# Looks up a title's MDBList score (and its IMDb sub-rating, if MDBList has
# one) via MDBList's API (server-side, via Control Panel). Uses the
# standalone MDBLIST_KEY .env secret - no separate key/account needed.
function stack-rating-mdblist --description 'Look up a title''s MDBList score'
    if test (count $argv) -lt 1
        echo "Usage: stack-rating-mdblist <imdb-id>" >&2
        return 1
    end
    set -l imdb_id $argv[1]
    __stack_api GET "/api/ratings/mdblist?imdb_id=$imdb_id"
end
