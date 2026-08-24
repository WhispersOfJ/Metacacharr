function stack-plex-deep-media-analysis --description 'Run full deep media analysis across every library (loudness, chapter thumbs, markers, voice activity)'
    __stack_api POST /api/plex/butler/deep-media-analysis
end
