# Usage: stack-plex <scan|empty-trash|optimize-db|clean-bundles>
function stack-plex --description 'Trigger a Plex maintenance action'
    if test (count $argv) -ne 1; or not contains -- $argv[1] scan empty-trash optimize-db clean-bundles
        echo "Usage: stack-plex <scan|empty-trash|optimize-db|clean-bundles>" >&2
        return 1
    end
    __stack_api POST "/api/plex/$argv[1]"
end
