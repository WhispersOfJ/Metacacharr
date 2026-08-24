# Usage: stack-letterboxd-radarr-history
function stack-letterboxd-radarr-history --description 'Show recent Letterboxd sync run history'
    __stack_api GET "/api/arr/letterboxd/history"
end
