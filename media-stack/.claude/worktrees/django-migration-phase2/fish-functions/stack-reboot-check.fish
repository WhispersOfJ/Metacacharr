# Usage: stack-reboot-check
# Checks for a pending-reboot marker (/var/run/reboot-required, used by
# some distros/tools) and cross-references stack-kernel-check - a single
# "do I need to reboot" answer instead of checking both separately.
function stack-reboot-check --description 'Check whether this host needs a reboot'
    set -l needed 0
    if test -f /var/run/reboot-required
        echo "[FAIL] /var/run/reboot-required marker present"
        set needed 1
    end
    if not stack-kernel-check >/dev/null 2>&1
        echo "[FAIL] running kernel does not match the installed one"
        set needed 1
    end
    if test $needed -eq 0
        echo "No reboot needed."
    else
        echo "Reboot recommended."
    end
    return $needed
end
