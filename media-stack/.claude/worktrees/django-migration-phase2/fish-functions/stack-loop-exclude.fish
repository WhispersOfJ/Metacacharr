# Usage: stack-loop-exclude <movie-id> [-y|--yes]
# Adds a Radarr movie to Exclusions - the durable fix for a movie that gets
# re-monitored by import-list syncs after stack-loop-unmonitor.
# Radarr only; Sonarr has no equivalent exclusion list for episodes.
function stack-loop-exclude --description 'Add a Radarr movie to Exclusions'
    argparse yes y -- $argv
    or return 1
    if test (count $argv) -lt 1
        echo "Usage: stack-loop-exclude <movie-id> [-y|--yes]" >&2
        return 1
    end
    set -l movie_id $argv[1]
    set -l app radarr
    if not set -q _flag_yes; and not set -q _flag_y
        read -l -P "Exclude $app movie $movie_id from all import lists? [y/N] " confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST "/api/arr/$app/exclude" "{\"movieId\": $movie_id}"
end
