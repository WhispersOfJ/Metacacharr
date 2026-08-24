function stack-plex-clean-cache-files --description 'Delete old Plex cache files'
    __stack_api POST /api/plex/butler/clean-cache-files
end
