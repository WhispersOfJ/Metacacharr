# Private helper: validate an Arr instance name. Every stack-* command
# that takes an app argument funnels through this, so the accepted
# spellings are defined once instead of drifting across separate
# `contains` guards.
#
# radarr_anime/sonarr_anime were retired 2026-08-18 (Plan 3 consolidation,
# merged into these base instances) - radarr/sonarr are the only two Arr
# instances in this stack now, so the --container normalization (which
# used to swap radarr_anime's underscore for radarr-anime's Docker-name
# hyphen) has nothing left to do; both spellings key the same instance.
#
# Usage: __stack_arr_app <name> [--container]
# Prints the normalized name and returns 0, or prints nothing and
# returns 1 if the name is not an Arr instance. Callers test the return
# value; the guard reads `not __stack_arr_app $argv[1] >/dev/null`.
function __stack_arr_app
    argparse container -- $argv
    or return 1
    if test (count $argv) -ne 1
        return 1
    end
    set -l key
    switch $argv[1]
        case radarr
            set key radarr
        case sonarr
            set key sonarr
        case '*'
            return 1
    end
    echo $key
end
