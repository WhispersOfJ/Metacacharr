function stack-plex-refresh-local-media --description 'Refresh local media file changes'
    __stack_api POST /api/plex/butler/refresh-local-media
end
