# Usage: stack-rating-imdb <imdb-id>
# Looks up a title's IMDb rating via OMDb (server-side, via Control Panel).
# Uses the standalone OMDB_KEY .env secret - no separate key/account needed.
function stack-rating-imdb --description 'Look up a title''s IMDb rating'
    if test (count $argv) -lt 1
        echo "Usage: stack-rating-imdb <imdb-id>" >&2
        return 1
    end
    set -l imdb_id $argv[1]
    __stack_api GET "/api/ratings/imdb?imdb_id=$imdb_id"
end
