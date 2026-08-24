function stack-plex-generate-intro-markers --description 'Generate intro markers for eligible media'
    __stack_api POST /api/plex/butler/generate-intro-markers
end
