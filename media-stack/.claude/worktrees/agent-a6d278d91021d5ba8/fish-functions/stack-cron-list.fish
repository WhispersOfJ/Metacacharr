# Usage: stack-cron-list
# Consolidated view of every scheduled job on this host - system-level
# systemd timers, user-level systemd timers (stack-*.timer among them),
# and any real crontab entries - in one place instead of three separate
# commands.
function stack-cron-list --description 'List all scheduled jobs: system timers, user timers, and crontabs'
    echo "=== System timers ==="
    systemctl list-timers --all --no-legend 2>/dev/null
    echo "=== User timers ==="
    systemctl --user list-timers --all --no-legend 2>/dev/null
    echo "=== User crontab ==="
    crontab -l 2>/dev/null; or echo "  (none)"
    echo "=== Root crontab ==="
    sudo -n crontab -l 2>/dev/null; or echo "  (none, or no permission)"
end
