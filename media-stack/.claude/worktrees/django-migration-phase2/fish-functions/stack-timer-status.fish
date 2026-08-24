# Usage: stack-timer-status
# Enabled state + last-run result for every stack-*.timer unit, so a
# silently-broken timer (like the %h/Stack path bug found and fixed this
# session - every stack-*.timer fired on schedule but its service failed
# every time) surfaces without manually parsing raw output. Uses
# list-unit-files rather than list-timers for the unit name list -
# list-timers' columns are unreliable to parse positionally since its
# NEXT/LAST fields are themselves multi-word datetimes, which silently
# shifted ACTIVATES (the service name) into the slot this originally
# expected UNIT (the timer name) to be in.
function stack-timer-status --description 'Check stack-*.timer units are enabled and their last run succeeded'
    set -l timers (systemctl --user list-unit-files 'stack-*.timer' --no-legend 2>/dev/null | awk '{print $1}')
    if test (count $timers) -eq 0
        echo "No stack-*.timer units found - installed? (see HOWTO.md's systemd setup step)"
        return 1
    end
    set -l problems 0
    for timer in $timers
        set -l service (string replace -r '\.timer$' '.service' -- $timer)
        set -l enabled (systemctl --user is-enabled "$timer" 2>/dev/null)
        set -l result (systemctl --user show "$service" --property=Result --value 2>/dev/null)
        if test "$enabled" = "enabled" -a \( "$result" = "success" -o -z "$result" \)
            set -l last (test -z "$result"; and echo "never run yet"; or echo "$result")
            echo "[ok]   $timer (last run: $last)"
        else
            echo "[FAIL] $timer - enabled=$enabled last_result=$result"
            set problems (math $problems + 1)
        end
    end
    if test $problems -gt 0
        echo "$problems timer(s) need attention."
    end
    return $problems
end
