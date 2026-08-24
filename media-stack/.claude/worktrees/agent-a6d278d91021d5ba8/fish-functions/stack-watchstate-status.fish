# Usage: stack-watchstate-status
# WatchState's sync state: how many items it tracks, when the scheduled import
# last ran and when it runs next, and whether one is queued right now.
#
# Also reports whether export is enabled on the Plex backend. It is off by
# design - export writes watch state back INTO Plex, and Plex is the only
# backend here - so seeing it on means something flipped it.
function stack-watchstate-status --description 'WatchState sync state, tracked items, import schedule'
    __stack_api GET /api/watchstate/status
end
