# Usage: stack-zombie-check
# Lists any zombie/defunct processes and their parent - a zombie itself
# is harmless, but persistent ones point at a parent that never reaps
# its children, worth tracking down.
function stack-zombie-check --description 'Check for zombie/defunct processes'
    set -l zombies (ps -eo pid,ppid,stat,comm | awk '$3 ~ /Z/')
    if test (count $zombies) -eq 0
        echo "No zombie processes."
        return 0
    end
    echo "PID    PPID   STAT  COMM"
    for line in $zombies
        echo "$line"
    end
end
