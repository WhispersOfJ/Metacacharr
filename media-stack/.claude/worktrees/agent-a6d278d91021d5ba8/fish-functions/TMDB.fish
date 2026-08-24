function TMDB --wraps='cd /home/daddybear/Claude/media-stack && python3 scripts/audit-tmdb-links.py --library Movies --csv /tmp/tmdb_audit_movies.csv' --description 'alias TMDB=cd /home/daddybear/Claude/media-stack && python3 scripts/audit-tmdb-links.py --library Movies --csv /tmp/tmdb_audit_movies.csv'
    cd /home/daddybear/Claude/media-stack && python3 scripts/audit-tmdb-links.py --library Movies --csv /tmp/tmdb_audit_movies.csv $argv
end
