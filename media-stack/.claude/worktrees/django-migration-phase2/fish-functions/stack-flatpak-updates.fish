# Usage: stack-flatpak-updates [--apply]
# Lists pending Flatpak updates; --apply actually runs them after a
# confirmation prompt.
function stack-flatpak-updates --description 'List (or apply) pending Flatpak updates'
    if not type -q flatpak
        echo "flatpak not installed." >&2
        return 1
    end
    set -l pending (flatpak remote-ls --updates 2>/dev/null)
    if test (count $pending) -eq 0
        echo "No pending Flatpak updates."
        return 0
    end
    for line in $pending
        echo "  $line"
    end
    if contains -- --apply $argv
        read -l -P "Apply Flatpak updates now? [y/N] " confirm
        if string match -qr '^[Yy]' -- $confirm
            flatpak update -y
        else
            echo "Aborted."
        end
    end
end
