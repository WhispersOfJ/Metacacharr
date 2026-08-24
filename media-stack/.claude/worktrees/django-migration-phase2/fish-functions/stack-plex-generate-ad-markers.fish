function stack-plex-generate-ad-markers --description 'Generate ad-break markers for eligible media'
    __stack_api POST /api/plex/butler/generate-ad-markers
end
