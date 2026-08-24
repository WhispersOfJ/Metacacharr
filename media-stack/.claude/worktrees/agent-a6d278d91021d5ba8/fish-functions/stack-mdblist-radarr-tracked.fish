# Usage: stack-mdblist-radarr-tracked
function stack-mdblist-radarr-tracked --description 'List every MDBList list registered for nightly sync'
    __stack_api GET "/api/mdblist/tracked"
end
