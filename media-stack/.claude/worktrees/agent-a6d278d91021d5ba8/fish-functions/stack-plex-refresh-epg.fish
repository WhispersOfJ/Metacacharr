function stack-plex-refresh-epg --description 'Refresh Live TV/DVR EPG guide data'
    __stack_api POST /api/plex/butler/refresh-epg
end
