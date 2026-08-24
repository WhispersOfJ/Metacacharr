# Usage: stack-arr-clear-blocklist <radarr|sonarr> [-y|--yes]
# Clears every blocklisted release, not just what stack-arr-blocklist shows.
# Confirms first unless -y is given.
function stack-arr-clear-blocklist --description 'Clear every blocklisted release in Radarr/Sonarr'
    if test (count $argv) -lt 1; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-arr-clear-blocklist <radarr|sonarr> [-y|--yes]" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    if not contains -- -y $argv; and not contains -- --yes $argv
        read -l -P "This clears EVERY blocklisted release in $app. Continue? [y/N] " confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST "/api/arr/$app/blocklist/clear"
end
