# Usage: stack-plex-butler <task>
# Fires one Plex Butler maintenance task on demand. Run with no args (or
# an unknown task) to see the full list Control Panel accepts - kept here
# rather than duplicated, so this list can't drift out of sync with
# control-panel/app.py's PLEX_BUTLER_TASKS.
function stack-plex-butler --description 'Trigger a named Plex Butler task on demand'
    set -l tasks automatic-updates backup-database clean-log-files generate-ad-markers \
        generate-credits-markers generate-intro-markers generate-voice-activity \
        clean-cache-files deep-media-analysis garbage-collect-blobs garbage-collect-media \
        generate-chapter-thumbs generate-media-index loudness-analysis music-analysis \
        process-assets refresh-epg refresh-libraries refresh-local-media upgrade-media-analysis
    if test (count $argv) -ne 1; or not contains -- $argv[1] $tasks
        echo "Usage: stack-plex-butler <task>" >&2
        echo "Known tasks: $tasks" >&2
        echo "(optimize-db / clean-bundles have their own stack-plex subcommands, not this one)" >&2
        return 1
    end
    __stack_api POST "/api/plex/butler/$argv[1]"
end
