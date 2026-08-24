# Usage: stack-watchstate-import-now
# Queues an out-of-schedule import from Plex.
#
# Queued, not run. WatchState enqueues an event and its own dispatcher picks it
# up within a minute, so this returns immediately and the result shows up in
# stack-watchstate-status, not here.
#
# The scheduled import is not a substitute for this and this is not a
# substitute for the webhook - all three paths stay on deliberately, because
# webhooks drop events (upstream's own warning).
function stack-watchstate-import-now --description 'Queue an out-of-schedule WatchState import from Plex'
    __stack_api POST /api/watchstate/import '{}'
end
