# Usage: stack-pkg-orphans [--remove]
# Lists orphaned packages (installed as a dependency, nothing depends on
# them anymore). --remove actually removes them after a confirmation
# prompt; without it, this is read-only.
function stack-pkg-orphans --description 'List (or remove) orphaned pacman packages'
    if not type -q pacman
        echo "Not an Arch-based host (no pacman found)." >&2
        return 1
    end
    set -l orphans (pacman -Qdtq 2>/dev/null)
    if test (count $orphans) -eq 0
        echo "No orphaned packages."
        return 0
    end
    echo (count $orphans)" orphaned package(s):"
    for pkg in $orphans
        echo "  $pkg"
    end
    if contains -- --remove $argv
        read -l -P "Remove all "(count $orphans)" orphaned package(s)? [y/N] " confirm
        if string match -qr '^[Yy]' -- $confirm
            sudo -n pacman -Rns --noconfirm $orphans
        else
            echo "Aborted."
        end
    end
end
