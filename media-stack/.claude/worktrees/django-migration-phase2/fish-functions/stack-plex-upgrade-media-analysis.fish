function stack-plex-upgrade-media-analysis --description 'Re-run analysis for items whose analysis version is outdated'
    __stack_api POST /api/plex/butler/upgrade-media-analysis
end
