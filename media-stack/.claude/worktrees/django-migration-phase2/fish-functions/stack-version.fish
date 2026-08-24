function stack-version --description 'README''s declared version + live container count'
    __stack_api GET /api/version
end
