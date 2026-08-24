function stack-perms-check --description 'Find config files unreadable by group/other (won''t be backed up)'
    __stack_api GET /api/perms-check
end
