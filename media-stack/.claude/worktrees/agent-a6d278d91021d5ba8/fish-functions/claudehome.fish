function claudehome --wraps='cd /home/bear/Claude && claude --dangerously-skip-permissions --add-dir /home/bear/Claude' --description 'alias claudehome=cd /home/bear/Claude && claude --dangerously-skip-permissions --add-dir /home/bear/Claude'
    cd /home/bear/Claude && claude --dangerously-skip-permissions --add-dir /home/bear/Claude $argv
end
