# Usage: stack-pkg-clean-cache [keep-N, default 3]
# Vacuums pacman's package cache down to the last N versions of each
# package (paccache -r), instead of it growing unbounded in /var/cache/pacman.
function stack-pkg-clean-cache --description 'Vacuum pacman cache, keeping the last N versions per package'
    if not type -q paccache
        echo "paccache not found (pacman-contrib not installed)." >&2
        return 1
    end
    set -l keep 3
    test (count $argv) -ge 1; and set keep $argv[1]
    sudo -n paccache -rk $keep
end
