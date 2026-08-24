# Usage: stack-plex-butler-all
# Fires every Plex Butler maintenance task Plex's own Settings > Manage >
# Butler screen offers, one at a time - the 19 named tasks stack-plex-butler
# already wraps, plus optimize-db and clean-bundles (stack-plex's own
# subcommands - they're Butler tasks too, just with dedicated routes since
# they predate stack-plex-butler). Sequential, not parallel: these are real
# maintenance jobs against the same Plex DB/FUSE mount that just recovered
# from a stale-handle incident - firing 21 of them at once risks re-creating
# that contention, firing them one request at a time does not (each POST
# just queues the task in Plex's own scheduler; it doesn't block on
# completion).
function stack-plex-butler-all --description 'Trigger every Plex Butler maintenance task, one at a time'
    set -l tasks automatic-updates backup-database clean-log-files generate-ad-markers \
        generate-credits-markers generate-intro-markers generate-voice-activity \
        clean-cache-files deep-media-analysis garbage-collect-blobs garbage-collect-media \
        generate-chapter-thumbs generate-media-index loudness-analysis music-analysis \
        process-assets refresh-epg refresh-libraries refresh-local-media upgrade-media-analysis
    for t in $tasks
        echo "-- $t --"
        stack-plex-butler $t
    end
    echo "-- optimize-db --"
    stack-plex optimize-db
    echo "-- clean-bundles --"
    stack-plex clean-bundles
end
