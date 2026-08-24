# Usage: stack-loop-unmonitor <radarr|sonarr> <id> [-y|--yes]
# Unmonitors a movie (Radarr) or episode (Sonarr) by id - the fix for a
# confirmed loop candidate. Confirms first unless -y is given.
#
# For Radarr this is often not enough on its own: an import list sync can
# re-monitor the movie afterwards. stack-loop-exclude is the durable fix.
function stack-loop-unmonitor --description 'Unmonitor a looping movie or episode by id'
    if test (count $argv) -lt 2; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-loop-unmonitor <radarr|sonarr> <id> [-y|--yes]" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    set -l item_id $argv[2]
    if not contains -- -y $argv; and not contains -- --yes $argv
        read -l -P "Unmonitor $app item $item_id? [y/N] " confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST "/api/arr/$app/unmonitor" "{\"ids\": [$item_id]}"
end
