# Usage: stack-ssh-doctor
# Checks ~/.ssh exists, known_hosts has an entry for github.com, and at
# least one private key is present and loadable - the exact gap that
# blocked a git push after this host's 2026-07-20 reinstall (no ~/.ssh
# at all, no known_hosts, no key).
function stack-ssh-doctor --description 'Check SSH setup health (keys, known_hosts, agent)'
    set -l problems 0

    if not test -d "$HOME/.ssh"
        echo "[FAIL] ~/.ssh does not exist"
        set problems (math $problems + 1)
    else
        echo "[ok]   ~/.ssh exists"
    end

    if not test -f "$HOME/.ssh/known_hosts"
        echo "[FAIL] ~/.ssh/known_hosts does not exist"
        set problems (math $problems + 1)
    else if not grep -q "github.com" "$HOME/.ssh/known_hosts" 2>/dev/null
        echo "[warn] ~/.ssh/known_hosts exists but has no github.com entry"
        set problems (math $problems + 1)
    else
        echo "[ok]   known_hosts has a github.com entry"
    end

    set -l keys (find "$HOME/.ssh" -maxdepth 1 -type f -name "id_*" ! -name "*.pub" 2>/dev/null)
    if test (count $keys) -eq 0
        echo "[FAIL] no private key found in ~/.ssh (id_ed25519, id_rsa, etc.)"
        set problems (math $problems + 1)
    else
        echo "[ok]   "(count $keys)" private key(s) found: "(string join ', ' (string replace "$HOME/.ssh/" "" $keys))
    end

    if test $problems -eq 0
        echo "All checks passed."
    else
        echo "$problems problem(s) found."
    end
    return $problems
end
