#!/bin/bash
# Trivy pre-commit hook
# Runs before committing docker-compose.yml to catch CVEs early
# Install: ln -sf ../../scripts/trivy-pre-commit.sh .git/hooks/pre-commit

set -e

# Only check if docker-compose.yml was modified
if ! git diff --cached --name-only | grep -q "docker-compose.yml"; then
  exit 0
fi

echo "🔍 Trivy pre-commit check (docker-compose.yml)"

if ! command -v trivy &> /dev/null; then
  echo "⚠️  Trivy not installed, skipping pre-commit check"
  echo "   Install: curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh"
  exit 0
fi

# Extract staged images (only modified ones)
STAGED_IMAGES=$(git diff --cached -U0 docker-compose.yml | grep -oP '^\+.*image:\s+\K[^@\n]+' | sort -u || true)

if [ -z "$STAGED_IMAGES" ]; then
  exit 0
fi

echo "📦 Checking staged image changes:"
echo "$STAGED_IMAGES" | sed 's/^/  - /'
echo ""

CRITICAL_FOUND=0
HIGH_FOUND=0

for IMAGE in $STAGED_IMAGES; do
  echo -n "  Scanning $IMAGE... "
  
  # Run trivy scan
  TRIVY_OUTPUT=$(trivy image --format json --severity CRITICAL,HIGH "$IMAGE" 2>/dev/null || echo "{}")
  
  # Count vulnerabilities
  CRIT=$(echo "$TRIVY_OUTPUT" | jq '[.Results[]?.Vulnerabilities[]? | select(.Severity=="CRITICAL")] | length' 2>/dev/null || echo 0)
  HIGH=$(echo "$TRIVY_OUTPUT" | jq '[.Results[]?.Vulnerabilities[]? | select(.Severity=="HIGH")] | length' 2>/dev/null || echo 0)
  
  CRITICAL_FOUND=$((CRITICAL_FOUND + CRIT))
  HIGH_FOUND=$((HIGH_FOUND + HIGH))
  
  if [ "$CRIT" -gt 0 ]; then
    echo "🔴 CRITICAL: $CRIT"
  elif [ "$HIGH" -gt 0 ]; then
    echo "🟠 HIGH: $HIGH"
  else
    echo "✅ OK"
  fi
done

echo ""

# Block on CRITICAL
if [ "$CRITICAL_FOUND" -gt 0 ]; then
  echo "❌ COMMIT BLOCKED: $CRITICAL_FOUND CRITICAL CVEs found"
  echo ""
  echo "   Fix by:"
  echo "   1. Identify affected images (see scan above)"
  echo "   2. Find patched versions (Docker Hub, Quay.io)"
  echo "   3. Update digests in docker-compose.yml"
  echo "   4. Re-run trivy locally to verify"
  echo ""
  echo "   Or to skip this check:"
  echo "   git commit --no-verify"
  exit 1
fi

# Warn on HIGH (but allow)
if [ "$HIGH_FOUND" -gt 0 ]; then
  echo "⚠️  WARNING: $HIGH_FOUND HIGH CVEs found (commit allowed)"
  echo "   Consider updating images to reduce CVEs"
  echo "   Run: ./scripts/trivy-scan.sh"
  echo ""
fi

echo "✅ Pre-commit check passed"
exit 0
