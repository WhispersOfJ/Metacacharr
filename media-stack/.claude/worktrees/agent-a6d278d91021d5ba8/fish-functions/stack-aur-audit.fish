# Usage: stack-aur-audit
# Cross-checks installed packages against known Arch security advisories
# via arch-audit if present; otherwise falls back to just listing
# foreign (AUR/manually-installed) packages and their install dates,
# since those are the ones without a distro security-tracking net at all.
function stack-aur-audit --description 'Check installed packages against Arch security advisories (or list AUR packages)'
    if type -q arch-audit
        arch-audit
        return $status
    end
    echo "arch-audit not installed - showing foreign (AUR/manual) packages instead:" >&2
    pacman -Qm
end
