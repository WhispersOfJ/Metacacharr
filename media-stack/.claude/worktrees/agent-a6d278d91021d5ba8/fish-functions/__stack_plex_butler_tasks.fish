# Private helper: the Butler task names stack-plex-butler accepts, read from
# the function itself so the list cannot drift from what it validates.
function __stack_plex_butler_tasks
    set -l src /home/bear/Claude/media-stack/fish-functions/stack-plex-butler.fish
    test -f $src; or return 1
    # `set -l tasks a b c \` plus its continuation lines, up to the line
    # that does not end in a backslash.
    set -l collecting 0
    for line in (cat $src)
        if string match -qr '^\s*set -l tasks ' -- $line
            set collecting 1
            set line (string replace -r '^\s*set -l tasks ' '' -- $line)
        else if test $collecting -eq 0
            continue
        end
        set -l more (string match -qr '\\\\$' -- $line; and echo 1; or echo 0)
        printf '%s\n' (string split ' ' -- (string trim (string replace -r '\\\\$' '' -- $line)))
        test $more -eq 0; and break
    end
end
