function stack-plex-generate-credits-markers --description 'Generate end-credits markers for eligible media'
    __stack_api POST /api/plex/butler/generate-credits-markers
end
