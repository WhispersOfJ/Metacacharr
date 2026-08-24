function stack-plex-garbage-collect-media --description 'Garbage-collect unused library media records'
    __stack_api POST /api/plex/butler/garbage-collect-media
end
