# Usage: stack-service-failed
# systemctl --failed across both the system and user manager instances -
# a service silently crash-looping into "failed" state (system units)
# or the user-session equivalent (e.g. a broken stack-*.service) can sit
# unnoticed indefinitely without this.
function stack-service-failed --description 'List failed systemd units (system and user)'
    echo "=== System ==="
    systemctl --failed --no-legend 2>/dev/null
    echo "=== User ==="
    systemctl --user --failed --no-legend 2>/dev/null
end
