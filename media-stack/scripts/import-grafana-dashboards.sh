#!/bin/bash
# Import Grafana dashboards via API
# Imports pre-configured Loki log dashboards into Grafana

set -e

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASS="${GRAFANA_PASS:-media-stack-logging-secure-2026}"
DASHBOARD_DIR="./config/grafana/dashboards"

echo "═════════════════════════════════════════════════════════════════"
echo "Importing Grafana Dashboards"
echo "═════════════════════════════════════════════════════════════════"
echo ""
echo "Target: $GRAFANA_URL"
echo "User: $GRAFANA_USER"
echo "Dashboards directory: $DASHBOARD_DIR"
echo ""

# Check if Grafana is reachable
echo "Checking Grafana connectivity..."
if ! curl -s -f "$GRAFANA_URL/api/health" > /dev/null; then
  echo "❌ Cannot reach Grafana at $GRAFANA_URL"
  echo "   Make sure Grafana is running: docker compose ps grafana"
  exit 1
fi
echo "✅ Grafana is reachable"
echo ""

# Create basic auth header
echo "Authenticating with Grafana..."
BASIC_AUTH=$(echo -n "$GRAFANA_USER:$GRAFANA_PASS" | base64)
echo "✅ Using basic authentication"
echo ""

# Import each dashboard
DASHBOARDS=$(find "$DASHBOARD_DIR" -name "*.json" -type f | sort)
IMPORTED_COUNT=0
FAILED_COUNT=0

for DASHBOARD_FILE in $DASHBOARDS; do
  DASHBOARD_NAME=$(basename "$DASHBOARD_FILE" .json)
  echo -n "Importing: $DASHBOARD_NAME... "
  
  # Add some required fields for import
  DASHBOARD_JSON=$(jq '.dashboard |= . + {
    "id": null,
    "version": 0,
    "timezone": "browser",
    "refresh": "30s"
  }' "$DASHBOARD_FILE")
  
  # Import dashboard
  RESPONSE=$(curl -s -X POST \
    -H "Authorization: Basic $BASIC_AUTH" \
    -H "Content-Type: application/json" \
    -d "{\"dashboard\": $DASHBOARD_JSON, \"overwrite\": true}" \
    "$GRAFANA_URL/api/dashboards/db")
  
  # Check response
  STATUS=$(echo "$RESPONSE" | jq -r '.status' 2>/dev/null || echo "error")
  ID=$(echo "$RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
  
  if [ "$STATUS" == "success" ] || [ -n "$ID" ] && [ "$ID" != "null" ]; then
    echo "✅ (ID: $ID)"
    IMPORTED_COUNT=$((IMPORTED_COUNT + 1))
  else
    echo "❌"
    ERROR_MSG=$(echo "$RESPONSE" | jq -r '.message' 2>/dev/null || echo "Unknown error")
    echo "   Error: $ERROR_MSG"
    FAILED_COUNT=$((FAILED_COUNT + 1))
  fi
done

echo ""
echo "═════════════════════════════════════════════════════════════════"
echo "Import Summary"
echo "═════════════════════════════════════════════════════════════════"
echo "✅ Imported: $IMPORTED_COUNT"
echo "❌ Failed: $FAILED_COUNT"
echo ""

if [ $FAILED_COUNT -eq 0 ]; then
  echo "✅ All dashboards imported successfully!"
  echo ""
  echo "📊 Available Dashboards:"
  echo "  1. Loki - Logs Overview"
  echo "     URL: $GRAFANA_URL/d/loki-logs-overview"
  echo "     View: All container logs, error rates, trends"
  echo ""
  echo "  2. Loki - Import Pipeline"
  echo "     URL: $GRAFANA_URL/d/loki-import-pipeline"
  echo "     View: Radarr/Sonarr/Prowlarr/NzbDAV focused"
  echo ""
  exit 0
else
  echo "⚠️  Some dashboards failed to import"
  exit 1
fi
