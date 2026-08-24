# Usage: stack-journal-errors
# journalctl entries at error-or-worse priority since the last boot -
# summarized by unit, so a recurring problem shows its frequency instead
# of scrolling past it N times.
function stack-journal-errors --description 'Summarize error-level journal entries since last boot'
    journalctl -b -p err --no-pager -o short-iso 2>/dev/null | awk '{
        # Extract the unit name (bracketed or "name[pid]:" form) if present
        match($0, /[A-Za-z0-9_.-]+\[[0-9]+\]/)
        unit = (RSTART > 0) ? substr($0, RSTART, RLENGTH) : "unknown"
        count[unit]++
    } END {
        for (u in count) print count[u], u
    }' | sort -rn | while read -l n unit
        echo "$n  $unit"
    end
end
