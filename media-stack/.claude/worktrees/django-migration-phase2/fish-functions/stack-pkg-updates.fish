# Usage: stack-pkg-updates
# Pending pacman + AUR updates (via checkupdates, which queries the sync
# db without touching the local one - safe to run anytime, unlike
# `pacman -Sy` alone). Falls back gracefully if checkupdates/paru aren't
# installed rather than assuming this host's exact toolchain forever.
function stack-pkg-updates --description 'List pending pacman and AUR package updates'
    if not type -q pacman
        echo "Not an Arch-based host (no pacman found)." >&2
        return 1
    end
    set -l repo_updates
    if type -q checkupdates
        set repo_updates (checkupdates 2>/dev/null)
    else
        echo "checkupdates not found (pacman-contrib not installed) - skipping repo check." >&2
    end
    set -l aur_updates
    if type -q paru
        set aur_updates (paru -Qua 2>/dev/null)
    else if type -q yay
        set aur_updates (yay -Qua 2>/dev/null)
    end
    echo "Repo updates: "(count $repo_updates)
    for line in $repo_updates
        echo "  $line"
    end
    echo "AUR updates: "(count $aur_updates)
    for line in $aur_updates
        echo "  $line"
    end
end
