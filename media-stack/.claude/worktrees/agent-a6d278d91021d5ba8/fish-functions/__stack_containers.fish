# Private helper: container names for tab completion. Live from Docker so a
# newly-added service is completable the moment it is up, with the compose
# file as a fallback for a stopped/never-started service.
function __stack_containers
    set -l names (docker ps -a --format '{{.Names}}' 2>/dev/null)
    if test -n "$names"
        printf '%s\n' $names
        return 0
    end
    string match -r '^  ([a-z0-9][a-z0-9_.-]*):$' -- (cat /home/bear/Claude/media-stack/docker-compose.yml 2>/dev/null) \
        | string match -v -r '^  ' \
        | string trim
end
