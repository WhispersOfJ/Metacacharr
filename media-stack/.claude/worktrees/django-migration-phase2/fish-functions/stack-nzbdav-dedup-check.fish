# Usage: stack-nzbdav-dedup-check
# Verifies NzbDAV's api.duplicate-nzb-behavior is still mark-failed. Guards
# against the return of the (2)/(3)-suffix importBlocked bug, where a
# duplicate grab lands as "Title (2)" and the Arr app cannot import it.
function stack-nzbdav-dedup-check --description 'Verify NzbDAV duplicate-nzb-behavior is still mark-failed'
    __stack_api GET /api/nzbdav/dedup-config-check
end
