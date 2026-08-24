# Usage: stack-plex-analyze [library name ...]
# No args = every library. With args = just that one (case-insensitive
# match against its Plex title, e.g. "TV Shows"). Queues Plex's per-item
# deep analysis (loudness, chapter thumbnails, intro/credits/ad markers,
# voice activity) for the target library - scoped, unlike
# stack-plex-butler deep-media-analysis below which runs server-wide.
function stack-plex-analyze --description 'Queue deep media analysis on one Plex library, or all of them'
    if test (count $argv) -eq 0
        __stack_api POST /api/plex/analyze
        return
    end
    set -l library (string join ' ' $argv)
    set -l encoded (python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" $library)
    __stack_api POST "/api/plex/analyze?library=$encoded"
end
