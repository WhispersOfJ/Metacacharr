# Usage: stack-kernel-check
# Compares the running kernel against the installed one - if they
# differ, a reboot is needed to actually load the new kernel (a common
# silent gap: pacman -Syu "succeeds" but the old kernel keeps running).
function stack-kernel-check --description 'Check for a pending kernel-update reboot'
    set -l running (uname -r)
    set -l installed_pkg linux
    # CachyOS/most kernel-variant installs name their package after the
    # variant (linux-cachyos, linux-zen, etc.) rather than plain "linux" -
    # infer from the running kernel's own version string suffix.
    if string match -qr -- '-cachyos' "$running"
        set installed_pkg linux-cachyos
    else if string match -qr -- '-zen' "$running"
        set installed_pkg linux-zen
    else if string match -qr -- '-lts' "$running"
        set installed_pkg linux-lts
    end
    if not type -q pacman
        echo "Not an Arch-based host (no pacman found)." >&2
        return 1
    end
    set -l installed (pacman -Q $installed_pkg 2>/dev/null | string split ' ')[2]
    if test -z "$installed"
        echo "Couldn't determine installed kernel package version ($installed_pkg not found)." >&2
        return 1
    end
    echo "Running:   $running"
    echo "Installed: $installed ($installed_pkg)"
    if string match -q "*$installed*" -- "$running"
        echo "Up to date - no reboot needed."
    else
        echo "MISMATCH - a newer kernel is installed but not running. Reboot to apply it."
        return 1
    end
end
