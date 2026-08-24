# Usage: stack-claude-full-backup
# One-off full ~/Claude tree tar.zst (no excludes) into
# "~/Dropbox/Stack and Claude Backups", dated, not overwritten in place.
# sudo needed for container-owned files under media-stack/config. Named
# (not $status) since fish reserves $status for the last command's exit
# code and will refuse to assign to it.
function stack-claude-full-backup --description 'Full ~/Claude tar.zst backup to Dropbox (dated, no excludes)'
    set -l dest_dir "$HOME/Dropbox/Stack and Claude Backups"
    set -l dest "$dest_dir/Claude-full-backup-"(date +%Y%m%d)".tar.zst"
    set -l tmp "$dest.tmp"

    mkdir -p "$dest_dir"
    echo "Writing to: $dest"

    sudo -n tar --zstd -cf "$tmp" -C "$HOME" Claude
    set -l tar_status $status

    # tar exit 1 = some files changed mid-archive (live DB/config files) -
    # not fatal, archive is still complete. >=2 is a real failure.
    if test $tar_status -eq 0 -o $tar_status -eq 1
        sudo -n chown (id -u):(id -g) "$tmp"
        mv -f "$tmp" "$dest"
        if test $tar_status -eq 0
            echo "Backup completed successfully ("(du -h "$dest" | cut -f1)")"
        else
            echo "Backup completed (some live files changed mid-archive, tar exit 1 - archive is still complete) ("(du -h "$dest" | cut -f1)")"
        end
    else
        rm -f "$tmp"
        echo "Backup failed (tar exit $tar_status)" >&2
        return $tar_status
    end
end
