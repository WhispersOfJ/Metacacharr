function stack-plex-loudness-analysis --description 'Analyze audio loudness for volume leveling'
    __stack_api POST /api/plex/butler/loudness-analysis
end
