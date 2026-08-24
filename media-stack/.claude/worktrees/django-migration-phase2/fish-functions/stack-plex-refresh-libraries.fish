function stack-plex-refresh-libraries --description 'Refresh metadata for every library'
    __stack_api POST /api/plex/butler/refresh-libraries
end
