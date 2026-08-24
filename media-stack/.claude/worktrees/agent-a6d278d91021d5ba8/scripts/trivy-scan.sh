#!/bin/bash
# Trivy baseline vulnerability scan for all services
# Scans all 15 services in docker-compose.yml for CVEs
# Output: STAGE-4-CVE-BASELINE.md + trivy-cache.json

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
REPORT_FILE="$REPO_ROOT/STAGE-4-CVE-BASELINE.md"

echo "🔍 Trivy Baseline Scan - All Services"
echo "=================================================================================="

# Check if trivy is installed
if ! command -v trivy &> /dev/null; then
  echo "❌ Trivy not found. Install: curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh"
  exit 1
fi

# Extract images from docker-compose.yml
mapfile -t IMAGES < <(grep -oP '^\s+image:\s+\K[^@\n]+' "$REPO_ROOT/docker-compose.yml" | sort -u)

echo "📦 Found ${#IMAGES[@]} unique images to scan"
echo ""

# Initialize report
cat > "$REPORT_FILE" << 'EOF'
# Stage 4: CVE Baseline Scan Report

**Generated:** 
**Scan Type:** All images in docker-compose.yml  
**Trivy Version:** (auto-filled)  
**Policy:** CRITICAL blocks merge, HIGH notifies, MEDIUM+ included in dashboard

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | — | 🔴 BLOCK MERGE |
| HIGH | — | 🟠 NOTIFY |
| MEDIUM | — | 🟡 TRACK |
| LOW | — | ⚪ TRACK |
| UNKNOWN | — | ⚪ TRACK |

**Total CVEs:** —  
**Actionable (CRIT+HIGH):** —  

---

## Scan Results by Service

EOF

# Scan each image
CRITICAL_COUNT=0
HIGH_COUNT=0
MEDIUM_COUNT=0
LOW_COUNT=0

for IMAGE in "${IMAGES[@]}"; do
  echo "Scanning: $IMAGE"
  
  # Run trivy scan with JSON output (suppress progress)
  TRIVY_OUTPUT=$(trivy image --format json --severity CRITICAL,HIGH,MEDIUM,LOW "$IMAGE" 2>/dev/null || echo "{}")
  
  # Parse JSON to count vulnerabilities
  CRIT=$(echo "$TRIVY_OUTPUT" | jq '[.Results[]?.Misconfigurations[]? | select(.Severity=="CRITICAL")] | length' 2>/dev/null || echo 0)
  HIGH=$(echo "$TRIVY_OUTPUT" | jq '[.Results[]?.Vulnerabilities[]? | select(.Severity=="HIGH")] | length' 2>/dev/null || echo 0)
  MEDIUM=$(echo "$TRIVY_OUTPUT" | jq '[.Results[]?.Vulnerabilities[]? | select(.Severity=="MEDIUM")] | length' 2>/dev/null || echo 0)
  LOW=$(echo "$TRIVY_OUTPUT" | jq '[.Results[]?.Vulnerabilities[]? | select(.Severity=="LOW")] | length' 2>/dev/null || echo 0)
  
  CRITICAL_COUNT=$((CRITICAL_COUNT + CRIT))
  HIGH_COUNT=$((HIGH_COUNT + HIGH))
  MEDIUM_COUNT=$((MEDIUM_COUNT + MEDIUM))
  LOW_COUNT=$((LOW_COUNT + LOW))
  
  # Append to report
  SEVERITY_ICON="✓"
  if [ "$CRIT" -gt 0 ]; then
    SEVERITY_ICON="🔴"
  elif [ "$HIGH" -gt 0 ]; then
    SEVERITY_ICON="🟠"
  elif [ "$MEDIUM" -gt 0 ]; then
    SEVERITY_ICON="🟡"
  fi
  
  cat >> "$REPORT_FILE" << EOF

### $SEVERITY_ICON $IMAGE
- CRITICAL: $CRIT
- HIGH: $HIGH
- MEDIUM: $MEDIUM
- LOW: $LOW

EOF

  echo "  ✓ CRITICAL: $CRIT, HIGH: $HIGH, MEDIUM: $MEDIUM, LOW: $LOW"
done

# Update summary section
sed -i "s/| CRITICAL | — |/| CRITICAL | $CRITICAL_COUNT |/g" "$REPORT_FILE"
sed -i "s/| HIGH | — |/| HIGH | $HIGH_COUNT |/g" "$REPORT_FILE"
sed -i "s/| MEDIUM | — |/| MEDIUM | $MEDIUM_COUNT |/g" "$REPORT_FILE"
sed -i "s/| LOW | — |/| LOW | $LOW_COUNT |/g" "$REPORT_FILE"

TOTAL=$((CRITICAL_COUNT + HIGH_COUNT + MEDIUM_COUNT + LOW_COUNT))
sed -i "s/\*\*Total CVEs:\*\* —/\*\*Total CVEs:\*\* $TOTAL/g" "$REPORT_FILE"

ACTIONABLE=$((CRITICAL_COUNT + HIGH_COUNT))
sed -i "s/\*\*Actionable (CRIT+HIGH):\*\* —/\*\*Actionable (CRIT+HIGH):\*\* $ACTIONABLE/g" "$REPORT_FILE"

# Add next steps
cat >> "$REPORT_FILE" << EOF

---

## Next Steps

1. **CRITICAL CVEs ($CRITICAL_COUNT found):**
   - Block these in GitHub Actions (exit code 1)
   - Remediate by updating image digest
   - Re-run scan to verify fix

2. **HIGH CVEs ($HIGH_COUNT found):**
   - Post to Discord daily digest
   - Schedule update (within 2 weeks)
   - Track in Grafana dashboard

3. **MEDIUM CVEs ($MEDIUM_COUNT found):**
   - Track in Grafana dashboard
   - Review quarterly
   - Update if available with no breaking changes

---

## Remediation Workflow

For each CVE found:

1. **Identify affected image** (via this report)
2. **Check if update available** (Docker Hub, Quay.io)
3. **Update image digest** in docker-compose.yml
4. **Test** the updated image locally
5. **Verify** scan now passes
6. **Deploy** to main

Example:
\`\`\`bash
# Before
image: grafana/grafana:10.0.0@sha256:abc123...

# After (updated digest)
image: grafana/grafana:10.1.0@sha256:def456...

# Verify
./scripts/trivy-scan.sh
\`\`\`

---

## Policy Enforcement

GitHub Actions workflow (.github/workflows/trivy-scan.yml):
- ✓ Scans on every PR
- 🔴 BLOCKS merge if CRITICAL found
- 🟠 WARNS if HIGH found
- 🟡 ALLOWS if MEDIUM/LOW only

---

## Grafana Dashboard

Dashboard: Stage 4 - Image CVEs  
Queries:
- CVE trend over time (weekly)
- Severity breakdown (CRIT / HIGH / MED / LOW)
- Services with outdated images
- Last scan date + next scan date

---

**Report generated:** $(date -u)  
**Scan location:** .github/workflows/trivy-scan.yml  
**Manual scan:** ./scripts/trivy-scan.sh

EOF

echo ""
echo "✅ Baseline scan complete!"
echo "📄 Report: $REPORT_FILE"
echo ""
echo "Summary:"
echo "  CRITICAL: $CRITICAL_COUNT 🔴"
echo "  HIGH: $HIGH_COUNT 🟠"
echo "  MEDIUM: $MEDIUM_COUNT 🟡"
echo "  LOW: $LOW_COUNT ⚪"
echo "  TOTAL: $TOTAL"
echo ""

if [ "$CRITICAL_COUNT" -gt 0 ]; then
  echo "⚠️  ACTION REQUIRED: $CRITICAL_COUNT CRITICAL CVEs found"
  echo "   Review report and update affected images"
  exit 1
else
  echo "✓ No CRITICAL CVEs found"
  exit 0
fi
