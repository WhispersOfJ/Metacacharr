# Usage: stack-sonarr-fix-episode-monitoring
# Fixes any episode left unmonitored under a monitored Sonarr series/season -
# can happen after an import-list add, a partial re-add after a bulk delete,
# etc. Season 0 (specials/extras) is deliberately left alone.
function stack-sonarr-fix-episode-monitoring --description 'Fix unmonitored episodes under monitored Sonarr series'
    __stack_api POST "/api/arr/sonarr/monitor-episodes-fix"
end
