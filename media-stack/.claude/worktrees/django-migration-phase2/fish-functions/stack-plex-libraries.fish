function stack-plex-libraries --description 'List Plex library names (e.g. for stack-plex-empty-trash)'
    __stack_api GET /api/plex/libraries
end
