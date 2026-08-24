#!/usr/bin/env bash
# Shared Discord webhook notifier - used by backup-config.sh,
# check-container-health.sh, arr-app-backup.py's shell-callable peers, and
# systemd's OnFailure= hook on any unit that wants one. Silently no-ops if
# DISCORD_WEBHOOK_URL isn't set/configured yet, so nothing breaks for anyone
# running this stack without alerting set up.
#
# Posts a real embed (title/color/timestamp/footer) instead of flat text -
# same visual style plex-library-report.py and arr-app-backup.py already
# build directly for their own posts, extended here so every other script
# and the systemd OnFailure hook get it too, without taking on Notifiarr's
# cloud-relay dependency just for nicer formatting.
#
# Usage: notify-discord.sh "message text" [info|warn|error]
set -uo pipefail

cd "$(dirname "$0")/.." || exit

# Deliberately not `source .env` - some values contain literal `$` characters
# that bash's normal assignment expansion would try to interpret as parameter
# references (broke with "unbound variable" under set -u). grep+cut sidesteps
# that entirely since neither touches `$`.
env_get() { [ -f .env ] && grep -E "^${1}=" .env | head -1 | cut -d'=' -f2-; }
DISCORD_WEBHOOK_URL="$(env_get DISCORD_WEBHOOK_URL)"
HOST_IP="$(env_get HOST_IP)"

message="${1:-}"
level="${2:-info}"

[ -z "${DISCORD_WEBHOOK_URL:-}" ] && exit 0
[ "$DISCORD_WEBHOOK_URL" = "changeme" ] && exit 0
[ -z "$message" ] && exit 0

case "$level" in
error)
  title="🔴 Stack Error"
  color=15548997
  ;; # DISCORD_RED, matches arr-app-backup.py
warn)
  title="🟡 Stack Warning"
  color=15105570
  ;; # DISCORD_ORANGE, matches plex-library-report.py
*)
  title="🟢 Stack Notice"
  color=5763719
  ;; # DISCORD_GREEN, matches both of the above
esac

payload=$(python3 -c "
import json, sys
from datetime import datetime, timezone

title, color, host, message = sys.argv[1], int(sys.argv[2]), sys.argv[3] or 'Stack', sys.argv[4]
embed = {
    'title': title,
    'description': message,
    'color': color,
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'footer': {'text': host},
}
print(json.dumps({'embeds': [embed]}))
" "$title" "$color" "${HOST_IP:-Stack}" "$message")

curl -s -o /dev/null -X POST -H "Content-Type: application/json" \
  -d "$payload" "$DISCORD_WEBHOOK_URL"
