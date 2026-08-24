# Usage: stack-git-status-all
# One-shot `git status --short` across every git repo directly under
# ~/Claude - would have caught a stray untracked file or an unrelated
# in-progress edit sitting uncommitted faster than checking each repo
# by hand.
function stack-git-status-all --description 'git status --short across every repo under ~/Claude'
    for dir in $HOME/Claude/*/
        set -l repo (string trim -r -c / -- $dir)
        if test -d "$repo/.git"
            set -l status_lines (git -C "$repo" status --short 2>/dev/null)
            set -l branch (git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null)
            if test (count $status_lines) -eq 0
                echo (basename "$repo")" [$branch]: clean"
            else
                echo (basename "$repo")" [$branch]: "(count $status_lines)" change(s)"
                for line in $status_lines
                    echo "    $line"
                end
            end
        end
    end
end
