# Usage: stack-disk-health
# SMART health summary for every physical disk (via smartctl) - overall
# pass/fail plus reallocated-sector and pending-sector counts, the two
# earliest warning signs of a failing drive.
function stack-disk-health --description 'Show SMART health summary for all physical disks'
    if not type -q smartctl
        echo "smartctl not found (smartmontools not installed)." >&2
        return 1
    end
    set -l disks (lsblk -dno NAME,TYPE | awk '$2=="disk"{print $1}' | grep -v '^zram')
    if test (count $disks) -eq 0
        echo "No physical disks found via lsblk."
        return 1
    end
    for disk in $disks
        echo "=== /dev/$disk ==="
        set -l health (sudo -n smartctl -H /dev/$disk 2>/dev/null | grep -i "overall-health\|test result")
        echo "  $health"
        sudo -n smartctl -A /dev/$disk 2>/dev/null | grep -iE "reallocated_sector|pending_sector|reported_uncorrect" | while read -l line
            echo "  $line"
        end
    end
end
