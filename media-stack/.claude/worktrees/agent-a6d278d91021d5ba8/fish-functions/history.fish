# Fish command history, with timestamps - forwards $argv so subcommands
# like `history clear`/`history search ...` still work (fixed: previously
# dropped every argument and always just showed the dated listing).
function history
    builtin history --show-time='%F %T ' $argv
end
