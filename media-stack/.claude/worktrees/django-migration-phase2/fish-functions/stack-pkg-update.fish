# Usage: stack-pkg-update [--yes]
# Runs the actual system update (pacman -Syu, plus paru -Sua if an AUR
# helper is present). Prompts for confirmation first since this can
# break things - pass --yes to skip the prompt for scripted use.
function stack-pkg-update --description 'Run pacman/AUR system update (confirmation-gated)'
    if not type -q pacman
        echo "Not an Arch-based host (no pacman found)." >&2
        return 1
    end
    if not contains -- --yes $argv
        read -l -P "Run a full system update now? [y/N] " confirm
        if not string match -qr '^[Yy]' -- $confirm
            echo "Aborted."
            return 1
        end
    end
    sudo -n pacman -Syu --noconfirm
    set -l status_pacman $status
    if type -q paru
        paru -Sua --noconfirm
    else if type -q yay
        yay -Sua --noconfirm
    end
    return $status_pacman
end
