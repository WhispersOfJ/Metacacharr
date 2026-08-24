# Usage: stack-docker-disk-usage
# `docker system df -v`-style breakdown (images/containers/volumes/build
# cache) - which category is actually eating disk before reaching for a
# blanket `docker system prune`.
function stack-docker-disk-usage --description 'Show Docker disk usage broken down by category'
    docker system df
end
