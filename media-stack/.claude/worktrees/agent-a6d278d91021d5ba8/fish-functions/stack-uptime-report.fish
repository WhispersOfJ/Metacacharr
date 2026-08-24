# Usage: stack-uptime-report
# Uptime, load average, and whether the last shutdown was clean or a
# crash (via /run/systemd's own reboot marker vs an unexpected restart) -
# one glance instead of piecing together uptime + last + journalctl.
function stack-uptime-report --description 'Show uptime, load average, and last-boot cleanliness'
    uptime
    echo
    echo "Last boot:"
    who -b 2>/dev/null
    echo
    set -l last_shutdown (journalctl -b -1 --no-pager -n 5 2>/dev/null | grep -iE "reboot|shutdown|power" | tail -1)
    if test -n "$last_shutdown"
        echo "Last shutdown message: $last_shutdown"
    else
        echo "No previous-boot shutdown message found (journal may not span it)."
    end
end
