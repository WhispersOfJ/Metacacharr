# Usage: stack-queue-autofix
# Blocklists+re-searches failedPending items in Radarr/Sonarr and Radarr's
# importBlocked items, disables autoRedownloadFailed if a retry storm is
# detected, and reports NzbDAV queue health - the recurring 5-minute
# queue-monitoring loop's workflow in one call.
function stack-queue-autofix --description 'Blocklist+research stuck Radarr/Sonarr queue items, check NzbDAV health'
    __stack_api POST "/api/arr/queue-autofix"
end
