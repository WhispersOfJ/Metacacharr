function stack-status --description 'Show live state/health of every media-stack container'
    __stack_api GET /api/status
end
