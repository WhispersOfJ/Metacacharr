# Usage: stack-restart-all [-y|--yes]
# Restarts every container in the stack (~21+). Confirms first unless -y is
# given, mirroring the arm/confirm double-click the web UI itself uses for
# this same "danger zone" action.
function stack-restart-all --description 'Restart the whole stack (confirms first)'
    if not contains -- -y $argv; and not contains -- --yes $argv
        read -l -P 'This restarts EVERY container in the stack. Continue? [y/N] ' confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST /api/stack/restart-all
end
