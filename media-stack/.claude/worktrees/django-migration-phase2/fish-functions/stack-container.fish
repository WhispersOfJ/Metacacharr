# Usage: stack-container <restart|stop|start> <container-name>
function stack-container --description 'Restart/stop/start a single stack container'
    if test (count $argv) -ne 2; or not contains -- $argv[1] restart stop start
        echo "Usage: stack-container <restart|stop|start> <container-name>" >&2
        return 1
    end
    __stack_api POST "/api/container/$argv[2]/$argv[1]"
end
