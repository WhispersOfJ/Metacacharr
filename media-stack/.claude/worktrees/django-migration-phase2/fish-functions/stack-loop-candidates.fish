# Usage: stack-loop-candidates <radarr|sonarr>
# Titles or episodes looping in the queue-autofix history - 2+ downloadFailed
# events in the last N hours - with a suggested remediation for each.
# The companions are stack-loop-unmonitor (stops the loop) and
# stack-loop-exclude (stops import lists re-monitoring it afterwards).
function stack-loop-candidates --description 'Looping titles in the queue-autofix history, with remediation'
    if test (count $argv) -lt 1; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-loop-candidates <radarr|sonarr>" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    __stack_api GET "/api/arr/$app/loop-candidates"
end
