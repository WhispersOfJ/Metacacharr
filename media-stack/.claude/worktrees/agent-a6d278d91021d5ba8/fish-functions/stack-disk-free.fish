# Usage: stack-disk-free [warn-pct, default 80] [crit-pct, default 90]
# `df -h` for real filesystems only (excludes tmpfs/devtmpfs/overlay
# noise), with a pass/warn/fail mark per mount based on use percentage.
function stack-disk-free --description 'Show disk free space with warn/critical thresholds'
    set -l warn 80
    set -l crit 90
    test (count $argv) -ge 1; and set warn $argv[1]
    test (count $argv) -ge 2; and set crit $argv[2]
    df -h -x tmpfs -x devtmpfs -x overlay -x squashfs --output=target,size,used,avail,pcent | tail -n +2 | while read -l target size used avail pcent
        set -l pct (string replace '%' '' -- $pcent)
        set -l mark ok
        if test "$pct" -ge "$crit"
            set mark FAIL
        else if test "$pct" -ge "$warn"
            set mark warn
        end
        printf "[%-4s] %-20s %6s used / %6s avail (%s%%)\n" $mark $target $used $avail $pct
    end
end
