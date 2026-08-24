# Usage: stack-mdblist-radarr-history
function stack-mdblist-radarr-history --description 'Show recent MDBList sync run history'
    __stack_api GET "/api/mdblist/history"
end
