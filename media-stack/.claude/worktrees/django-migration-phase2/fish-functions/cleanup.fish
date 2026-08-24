# Cleanup local orphaned packages
function cleanup
    while pacman -Qdtq
        sudo pacman -R (pacman -Qdtq)
        # Fixed: was `-eq 1`, which only broke the retry loop on that one
        # specific exit code - any other failure (cancelled sudo prompt,
        # removal blocked by a dependent package, etc.) looped forever
        # re-prompting for a password. Break on any failure instead.
        if test "$status" -ne 0
            break
        end
    end
end
