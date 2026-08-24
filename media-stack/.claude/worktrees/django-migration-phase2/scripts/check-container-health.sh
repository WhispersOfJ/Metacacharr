#!/usr/bin/env bash
# Polls docker for unhealthy/restarting containers and posts to Discord only
# on a *change* in the unhealthy set (new failure, or recovery) - not on
# every poll, so a container stuck unhealthy for hours doesn't spam.
# Run periodically by systemd/stack-health-check.{service,timer}.
set -uo pipefail

cd "$(dirname "$0")/.." || exit

state_file="$HOME/.cache/stack-unhealthy-containers"
mkdir -p "$(dirname "$state_file")"
[ -f "$state_file" ] || touch "$state_file"

# Checked explicitly rather than relying on `set -e` (which the script
# doesn't use, on purpose - the diff/notify logic below needs to keep
# running even when comm/grep "fail" on empty input). Without this check, a
# failed `docker ps` (socket permission issue, daemon restart mid-poll,
# etc.) would previously produce an empty $current that silently compared
# equal to an also-empty $previous on first run, reporting "no problems"
# instead of "monitoring is blind right now" - the one failure mode where
# this script staying silent is actually the worst outcome.
if ! current=$(docker ps -a --filter "health=unhealthy" --filter "status=restarting" --format '{{.Names}}' | sort -u); then
  ./scripts/notify-discord.sh "Health check itself failed: 'docker ps' errored (socket permission or daemon issue?) - container monitoring is blind until this is fixed." error
  exit 1
fi
previous=$(cat "$state_file")

if [ "$current" = "$previous" ]; then
  exit 0
fi

newly_bad=$(comm -13 <(echo "$previous") <(echo "$current") 2>/dev/null | grep -v '^$' || true)
recovered=$(comm -23 <(echo "$previous") <(echo "$current") 2>/dev/null | grep -v '^$' || true)

if [ -n "$newly_bad" ]; then
  ./scripts/notify-discord.sh "Container(s) unhealthy/restarting: $(echo "$newly_bad" | tr '\n' ' ')" error
fi
if [ -n "$recovered" ]; then
  ./scripts/notify-discord.sh "Container(s) recovered: $(echo "$recovered" | tr '\n' ' ')" info
fi

echo "$current" >"$state_file"
