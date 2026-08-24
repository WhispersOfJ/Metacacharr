# Usage: stack-journal-size [--vacuum-size SIZE]
# Shows journald's on-disk usage; --vacuum-size trims it down to the
# given size (e.g. "500M") if it's grown larger than wanted.
function stack-journal-size --description 'Show (or vacuum) systemd-journald disk usage'
    argparse 'vacuum-size=' -- $argv
    or return 1
    journalctl --disk-usage
    if set -q _flag_vacuum_size
        sudo -n journalctl --vacuum-size=$_flag_vacuum_size
    end
end
