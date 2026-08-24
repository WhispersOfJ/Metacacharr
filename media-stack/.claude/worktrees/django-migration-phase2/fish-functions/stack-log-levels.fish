# Usage: stack-log-levels [reset]
function stack-log-levels --description 'Check (or reset) every Servarr app''s log level'
    if test (count $argv) -eq 0
        __stack_api GET /api/log-levels
    else if test $argv[1] = reset
        __stack_api POST /api/log-levels/reset
    else
        echo "Usage: stack-log-levels [reset]" >&2
        return 1
    end
end
