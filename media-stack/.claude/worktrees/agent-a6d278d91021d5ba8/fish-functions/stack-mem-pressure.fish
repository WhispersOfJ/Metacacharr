# Usage: stack-mem-pressure
# Kernel PSI (Pressure Stall Information) snapshot for memory, CPU, and
# IO - the "some"/"full" avg10/60/300 figures show actual resource
# contention over time, which raw free/top numbers don't capture at all.
function stack-mem-pressure --description 'Show kernel pressure-stall info for memory/CPU/IO'
    for resource in memory cpu io
        set -l path /proc/pressure/$resource
        if test -f $path
            echo "=== $resource ==="
            cat $path
        end
    end
end
