# Usage: stack-letterboxd-radarr-tracked
function stack-letterboxd-radarr-tracked --description 'List every Letterboxd list registered for nightly sync'
    __stack_api GET "/api/arr/letterboxd/tracked"
end
