function stack-plex-generate-media-index --description 'Generate media index files used for fast seeking'
    __stack_api POST /api/plex/butler/generate-media-index
end
