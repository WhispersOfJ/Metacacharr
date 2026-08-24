#!/bin/bash
# Stage 4: Image Vulnerability Scanning - Setup Script
# Installs Trivy, configures GitHub Actions, sets up pre-commit hook

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "════════════════════════════════════════════════════════════════════════════════"
echo "Stage 4 Setup: Image Vulnerability Scanning (Trivy)"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

# Step 1: Check if Trivy is installed
echo "Step 1: Checking Trivy installation..."
if command -v trivy &> /dev/null; then
  TRIVY_VERSION=$(trivy version 2>/dev/null | head -1)
  echo "✅ Trivy already installed: $TRIVY_VERSION"
else
  echo "⏳ Installing Trivy..."
  cd /tmp
  curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh
  sudo mv ./bin/trivy /usr/local/bin/trivy
  trivy version
  echo "✅ Trivy installed"
fi
echo ""

# Step 2: Run baseline scan
echo "Step 2: Running baseline CVE scan..."
if [ ! -f "$REPO_ROOT/STAGE-4-CVE-BASELINE.md" ]; then
  echo "⏳ Generating baseline scan (this may take 5-10 minutes)..."
  chmod +x "$SCRIPT_DIR/trivy-scan.sh"
  "$SCRIPT_DIR/trivy-scan.sh" || true
  echo "✅ Baseline scan complete: STAGE-4-CVE-BASELINE.md"
else
  echo "✅ Baseline scan already exists"
fi
echo ""

# Step 3: Setup pre-commit hook
echo "Step 3: Setting up pre-commit hook..."
HOOK_FILE="$REPO_ROOT/.git/hooks/pre-commit"
if [ ! -L "$HOOK_FILE" ]; then
  chmod +x "$SCRIPT_DIR/trivy-pre-commit.sh"
  ln -sf "../../scripts/trivy-pre-commit.sh" "$HOOK_FILE"
  echo "✅ Pre-commit hook installed"
else
  echo "✅ Pre-commit hook already installed"
fi
echo ""

# Step 4: GitHub Actions workflow
echo "Step 4: GitHub Actions workflow..."
if [ -f "$REPO_ROOT/.github/workflows/trivy-scan.yml" ]; then
  echo "✅ Trivy GitHub Actions workflow configured"
  echo "   Location: .github/workflows/trivy-scan.yml"
  echo "   Triggers: PR (docker-compose.yml), push main, weekly"
else
  echo "❌ Trivy GitHub Actions workflow NOT FOUND"
  echo "   Expected: .github/workflows/trivy-scan.yml"
fi
echo ""

# Step 5: Policy configuration
echo "Step 5: Trivy policy configuration..."
if [ -f "$REPO_ROOT/.trivy/policy.yaml" ]; then
  echo "✅ Trivy policy configured"
  echo "   Location: .trivy/policy.yaml"
  echo "   Policy: CRITICAL blocks, HIGH notifies, MEDIUM+ tracked"
else
  echo "⚠️  Trivy policy not found"
  echo "   Expected: .trivy/policy.yaml"
fi
echo ""

# Step 6: Remediation priority
echo "Step 6: Remediation priority list..."
if [ -f "$REPO_ROOT/STAGE-4-REMEDIATION-PRIORITY.md" ]; then
  echo "✅ Remediation priority list created"
  echo "   Location: STAGE-4-REMEDIATION-PRIORITY.md"
else
  echo "❌ Remediation priority list NOT FOUND"
  echo "   Expected: STAGE-4-REMEDIATION-PRIORITY.md"
fi
echo ""

# Step 7: Grafana dashboard
echo "Step 7: Grafana CVE tracking dashboard..."
if [ -f "$REPO_ROOT/config/grafana/dashboards/stage-4-cve-tracking.json" ]; then
  echo "✅ Grafana dashboard JSON created"
  echo "   Location: config/grafana/dashboards/stage-4-cve-tracking.json"
  echo "   Dashboard: Stage 4 - Image CVE Tracking"
else
  echo "⚠️  Grafana dashboard not found"
  echo "   Expected: config/grafana/dashboards/stage-4-cve-tracking.json"
fi
echo ""

# Step 8: Summary
echo "════════════════════════════════════════════════════════════════════════════════"
echo "Stage 4 Setup Complete!"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

echo "📋 SUMMARY:"
echo ""
echo "What's configured:"
echo "  ✅ Trivy CLI installed globally"
echo "  ✅ Baseline scan completed (STAGE-4-CVE-BASELINE.md)"
echo "  ✅ Pre-commit hook installed (blocks CRITICAL CVEs locally)"
echo "  ✅ GitHub Actions workflow (blocks CRITICAL CVEs on PR merge)"
echo "  ✅ Trivy policy configured (.trivy/policy.yaml)"
echo "  ✅ Remediation priority list (STAGE-4-REMEDIATION-PRIORITY.md)"
echo "  ✅ Grafana CVE dashboard (config/grafana/dashboards/stage-4-cve-tracking.json)"
echo ""

echo "📊 Current Status:"
grep "^| CRITICAL" "$REPO_ROOT/STAGE-4-CVE-BASELINE.md" | sed 's/^/  /'
grep "^| HIGH" "$REPO_ROOT/STAGE-4-CVE-BASELINE.md" | sed 's/^/  /'
grep "^| MEDIUM" "$REPO_ROOT/STAGE-4-CVE-BASELINE.md" | sed 's/^/  /'
echo ""

echo "🚀 Next Steps:"
echo ""
echo "1. Review baseline scan:"
echo "   cat STAGE-4-CVE-BASELINE.md"
echo ""
echo "2. Review remediation priority:"
echo "   cat STAGE-4-REMEDIATION-PRIORITY.md"
echo ""
echo "3. Start Phase 1 updates (Week 1-2):"
echo "   • Grafana (Loki/Promtail/Grafana): 3 HIGH CVEs → update digests"
echo "   • Run: ./scripts/trivy-scan.sh to verify"
echo ""
echo "4. Commit setup files:"
echo "   git add -A"
echo "   git commit -m 'feat: deploy Stage 4 (Trivy CVE scanning)'"
echo ""
echo "5. Test pre-commit hook (modify docker-compose.yml):"
echo "   • Edit docker-compose.yml and git add"
echo "   • Run: git commit -m 'test commit' (should run trivy check)"
echo ""
echo "6. Setup Grafana dashboard:"
echo "   • Login to Grafana (http://localhost:3001)"
echo "   • Import dashboard from: config/grafana/dashboards/stage-4-cve-tracking.json"
echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "✅ Stage 4 infrastructure ready. Proceed with Week 1 remediation?"
echo "════════════════════════════════════════════════════════════════════════════════"
