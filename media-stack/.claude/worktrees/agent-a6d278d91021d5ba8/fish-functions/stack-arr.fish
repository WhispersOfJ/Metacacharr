# Usage: stack-arr <radarr|sonarr> <rss-sync|search-missing|unstick|unstick-importing>
# unstick only acts on items the arr app itself flagged (warning/error).
# unstick-importing is a different failure mode: a download wedged in
# trackedDownloadState "importing" keeps trackedDownloadStatus "ok" the
# whole time, so it never lights up that flag and unstick never touches
# it - but since disk-access commands run through a single execution
# slot, one wedged import silently blocks every other item behind it.
# Checks whether the file's path exists at all, then reads the first few
# MB straight through the arr app's own container mount, to tell a
# genuinely dead article (fails, sometimes only after ~30s) or a
# vanished path from a merely-wedged slot (reads fine) - blocklists a
# dead article, clears a wedged slot or missing path without
# blocklisting (neither is evidence the release itself is bad), then
# re-searches either way.
function stack-arr --description 'Trigger an *arr app maintenance action'
    if test (count $argv) -ne 2
        echo "Usage: stack-arr <radarr|sonarr> <rss-sync|search-missing|unstick|unstick-importing>" >&2
        return 1
    end
    if not __stack_arr_app $argv[1] >/dev/null
        echo "Unknown app '$argv[1]' - use radarr or sonarr." >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    if not contains -- $argv[2] rss-sync search-missing unstick unstick-importing
        echo "Unknown action '$argv[2]' - use rss-sync, search-missing, unstick, or unstick-importing." >&2
        return 1
    end
    __stack_api POST "/api/arr/$app/$argv[2]"
end
