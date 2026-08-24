function stack-resource-check --description 'List containers missing mem_limit/cpus'
    __stack_api GET /api/resource-check
end
