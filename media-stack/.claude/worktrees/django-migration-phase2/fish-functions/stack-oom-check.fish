function stack-oom-check --description 'List containers Docker has recorded an OOM-kill for'
    __stack_api GET /api/oom-check
end
