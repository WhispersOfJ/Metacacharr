# Copy DIR1 DIR2
function copy
    set count (count $argv)
    if test "$count" = 2; and test -d "$argv[1]"
        set from (string trim --right --chars=/ -- $argv[1])
        set to $argv[2]
        command cp -r $from $to
    else
        command cp $argv
    end
end
