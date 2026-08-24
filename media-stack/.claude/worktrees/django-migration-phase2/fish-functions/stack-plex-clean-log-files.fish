function stack-plex-clean-log-files --description 'Delete old supplemental Plex log files'
    __stack_api POST /api/plex/butler/clean-log-files
end
