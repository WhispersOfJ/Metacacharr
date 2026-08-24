# Usage: stack-firewall-status
# Active nftables rule summary plus every port this host actually
# listens on - a quick "what's exposed" check without hand-parsing
# nft list ruleset or ss output separately.
function stack-firewall-status --description 'Show active nftables rules and listening ports'
    echo "=== nftables tables ==="
    sudo -n nft list tables 2>/dev/null; or echo "  (no nftables ruleset, or no permission)"
    echo "=== Listening ports ==="
    ss -tlnp 2>/dev/null | tail -n +2 | awk '{print $4, $NF}' | sort -u
end
