# Usage: stack-nzbdav-delete-failures
# On-demand version of the scripts/bearmount-prune-history.py job
# stack-bearmount-prune-history.timer already runs every 4h (script/unit
# names kept as "bearmount-prune-history" - installed systemd symlinks
# point at that exact path - even though it now prunes NzbDAV's history).
# Deletes every "Failed" entry from NzbDAV's history - a Failed row can
# block re-grabbing an NZB with a matching release name, so there's no
# reason to wait for the timer if you're stuck on this right now.
function stack-nzbdav-delete-failures --description 'Delete all Failed entries from NzbDAV history'
    __stack_api POST "/api/nzbdav/delete-failures"
end
