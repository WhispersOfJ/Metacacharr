#!/bin/bash
# Check upstream maintainers for new releases
# Monitors: hotio (Radarr/Sonarr/Prowlarr), seerr-team (Seerr), arabcoders (Unpackerr/WatchState)
# Alerts via Discord webhook on new versions found

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
STATE_FILE="$REPO_ROOT/.upstream-versions.json"
DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"

# Initialize state file if missing
if [ ! -f "$STATE_FILE" ]; then
  cat > "$STATE_FILE" << 'JSON'
{
  "last_checked": "never",
  "hotio_radarr": "unknown",
  "hotio_sonarr": "unknown",
  "hotio_prowlarr": "unknown",
  "seerr": "unknown",
  "unpackerr": "unknown",
  "watchstate": "unknown"
}
JSON
fi

echo "🔄 Checking upstream releases..."
echo "Last checked: $(jq -r .last_checked "$STATE_FILE")"
echo ""

# Helper: Get latest Docker Hub tag
get_docker_hub_tag() {
  local image="$1"
  curl -s "https://hub.docker.com/v2/repositories/$image/tags/?page_size=100" \
    | jq -r '.results[0].name' 2>/dev/null || echo "unknown"
}

# Helper: Get latest GitHub release
get_github_release() {
  local repo="$1"
  curl -s "https://api.github.com/repos/$repo/releases/latest" \
    -H "Authorization: token ${GITHUB_TOKEN:-}" \
    | jq -r '.tag_name' 2>/dev/null || echo "unknown"
}

# Check each upstream
declare -A new_versions

echo "📦 Checking hotio images..."
hotio_radarr=$(get_docker_hub_tag "hotio/radarr")
hotio_sonarr=$(get_docker_hub_tag "hotio/sonarr")
hotio_prowlarr=$(get_docker_hub_tag "hotio/prowlarr")

echo "  Radarr: $hotio_radarr"
echo "  Sonarr: $hotio_sonarr"
echo "  Prowlarr: $hotio_prowlarr"

old_radarr=$(jq -r .hotio_radarr "$STATE_FILE")
old_sonarr=$(jq -r .hotio_sonarr "$STATE_FILE")
old_prowlarr=$(jq -r .hotio_prowlarr "$STATE_FILE")

[ "$hotio_radarr" != "$old_radarr" ] && [ "$old_radarr" != "unknown" ] && new_versions["radarr"]="$old_radarr → $hotio_radarr"
[ "$hotio_sonarr" != "$old_sonarr" ] && [ "$old_sonarr" != "unknown" ] && new_versions["sonarr"]="$old_sonarr → $hotio_sonarr"
[ "$hotio_prowlarr" != "$old_prowlarr" ] && [ "$old_prowlarr" != "unknown" ] && new_versions["prowlarr"]="$old_prowlarr → $hotio_prowlarr"

echo ""
echo "🔍 Checking seerr-team/seerr..."
seerr=$(get_github_release "seerr-team/seerr")
echo "  Seerr: $seerr"
old_seerr=$(jq -r .seerr "$STATE_FILE")
[ "$seerr" != "$old_seerr" ] && [ "$old_seerr" != "unknown" ] && new_versions["seerr"]="$old_seerr → $seerr"

echo ""
echo "🔍 Checking arabcoders images..."
unpackerr=$(get_docker_hub_tag "hotio/unpackerr")
echo "  Unpackerr: $unpackerr"
old_unpackerr=$(jq -r .unpackerr "$STATE_FILE")
[ "$unpackerr" != "$old_unpackerr" ] && [ "$old_unpackerr" != "unknown" ] && new_versions["unpackerr"]="$old_unpackerr → $unpackerr"

echo ""
echo "🔍 Checking codeassassin/WatchState..."
watchstate=$(get_github_release "codeassassin/WatchState")
echo "  WatchState: $watchstate"
old_watchstate=$(jq -r .watchstate "$STATE_FILE")
[ "$watchstate" != "$old_watchstate" ] && [ "$old_watchstate" != "unknown" ] && new_versions["watchstate"]="$old_watchstate → $watchstate"

# Update state file
jq ".last_checked = \"$(date -u +'%Y-%m-%d %H:%M:%S')\" | \
    .hotio_radarr = \"$hotio_radarr\" | \
    .hotio_sonarr = \"$hotio_sonarr\" | \
    .hotio_prowlarr = \"$hotio_prowlarr\" | \
    .seerr = \"$seerr\" | \
    .unpackerr = \"$unpackerr\" | \
    .watchstate = \"$watchstate\"" \
    "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

echo ""
echo "════════════════════════════════════════════════════════════════"

if [ ${#new_versions[@]} -gt 0 ]; then
  echo "🎉 NEW VERSIONS FOUND!"
  echo ""
  for name in "${!new_versions[@]}"; do
    echo "  • $name: ${new_versions[$name]}"
  done
  echo ""
  
  # Alert via Discord if webhook configured
  if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    echo "📢 Alerting to Discord..."
    
    # Build Discord message
    updates=""
    for name in "${!new_versions[@]}"; do
      updates+="• **$name**: ${new_versions[$name]}\n"
    done
    
    curl -s -X POST "$DISCORD_WEBHOOK_URL" \
      -H 'Content-Type: application/json' \
      -d "{
        \"username\": \"Media Stack Updates\",
        \"embeds\": [
          {
            \"title\": \"🎉 Upstream Updates Available\",
            \"description\": \"New versions found for Phase 2-3 blockers\",
            \"color\": 3066993,
            \"fields\": [
              {
                \"name\": \"Updates\",
                \"value\": \"$updates\",
                \"inline\": false
              }
            ],
            \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
          }
        ]
      }" >/dev/null 2>&1
    
    echo "✓ Discord alert sent"
  fi
  
  exit 0
else
  echo "✓ No new versions (all current)"
  exit 0
fi
