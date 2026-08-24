# Usage: stack-pkg-history [N, default 20]
# Tail of pacman's transaction log (installs/removals/upgrades) - what
# actually changed on this system recently, without digging through the
# raw log file format by hand.
function stack-pkg-history --description 'Show recent pacman transaction log entries'
    set -l n 20
    test (count $argv) -ge 1; and set n $argv[1]
    if not test -f /var/log/pacman.log
        echo "No /var/log/pacman.log found." >&2
        return 1
    end
    grep -E '\[ALPM\] (installed|removed|upgraded)' /var/log/pacman.log | tail -n $n
end
