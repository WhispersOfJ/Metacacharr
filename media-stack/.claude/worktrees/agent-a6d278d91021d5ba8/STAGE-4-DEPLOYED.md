# Stage 4: Image Vulnerability Scanning (Trivy) - DEPLOYED ✓

**Deployed:** 2026-08-21  
**Commit:** 0e648b7  
**Status:** All scanning infrastructure running and healthy

---

## What's Running

| Component | Version | Purpose | Status |
|-----------|---------|---------|--------|
| **Trivy CLI** | 0.74.0 | Local CVE scanning | ✓ Installed |
| **GitHub Actions** | trivy-scan.yml | Automated PR/push scanning | ✓ Configured |
| **Pre-commit Hook** | trivy-pre-commit.sh | Block CRITICAL CVEs locally | ✓ Installed |
| **Policy Configuration** | .trivy/policy.yaml | CRITICAL blocks, HIGH warns | ✓ Configured |

---

## Baseline Scan Results

**Generated:** 2026-08-21  
**Total CVEs Detected:** 2043  
**Severity Breakdown:**

| Severity | Count | Status | Action |
|----------|-------|--------|--------|
| CRITICAL | 0 | ✅ SAFE | — |
| HIGH | 780 | 🟠 ACTION | Remediate over 4 weeks |
| MEDIUM | 842 | 🟡 TRACK | Quarterly review |
| LOW | 421 | ⚪ TRACK | Quarterly review |

**Top Affected Services (HIGH CVEs):**

1. **grafana/promtail:2.5.0** — 207 HIGH ← Week 1 priority
2. **grafana/grafana:10.0.0** — 138 HIGH ← Week 1 priority
3. **ghcr.io/seerr-team/seerr** — 84 HIGH ← Week 3 priority
4. **grafana/loki:2.5.0** — 98 HIGH ← Week 2 priority
5. **ghcr.io/arabcoders/watchstate:latest** — 79 HIGH ← Week 3 priority
6. **ghcr.io/hotio/radarr:release** — 48 HIGH ← Week 2 priority
7. **ghcr.io/hotio/prowlarr:release** — 48 HIGH ← Week 2 priority
8. **golift/unpackerr** — 53 HIGH ← Week 3 priority
9. **nickfedor/watchtower:1.20.3** — 10 HIGH ← Week 4 priority
10. **rclone/rclone:latest** — 8 HIGH ← Week 4 priority

**Services with Zero CVEs:**

- ✅ ghcr.io/cleanuparr/cleanuparr:2.10.5 (CLEAN)
- ✅ ghcr.io/infinidysk/infinidysk:latest (CLEAN)

---

## How It Works

### 1. Local Scanning (Pre-commit Hook)

Before you commit changes to `docker-compose.yml`:

```bash
# User attempts commit
$ git commit -m "update radarr image"

# Pre-commit hook runs automatically
🔍 Trivy pre-commit check (docker-compose.yml)
📦 Checking staged image changes:
  - ghcr.io/hotio/radarr:release
  Scanning ghcr.io/hotio/radarr:release... 🟠 HIGH: 48

⚠️  WARNING: 48 HIGH CVEs found (commit allowed)
   Consider updating images to reduce CVEs
   Run: ./scripts/trivy-scan.sh

✅ Pre-commit check passed
```

**Behavior:**
- 🟢 CRITICAL found? → ❌ BLOCKS commit (exit code 1)
- 🟡 HIGH found? → ⚠️  WARNING (allows commit)
- 🟢 MEDIUM/LOW? → ✅ CLEAN (allows commit)

### 2. Automated Scanning (GitHub Actions)

On every PR or push to `main`:

```yaml
Workflow: Trivy Image Security Scan
├── Trigger: PR (docker-compose.yml changes), push main, weekly schedule
├── Step 1: Extract images from docker-compose.yml
├── Step 2: Run Trivy on all images
├── Step 3: Generate SARIF report → GitHub Security tab
├── Step 4: Check CRITICAL count
│   ├── If CRITICAL > 0 → ❌ FAIL (blocks merge)
│   └── If CRITICAL = 0 → ✅ PASS (allows merge)
└── Step 5: Notify via Discord (HIGH/CRITICAL summary)
```

**Reports:**
- SARIF format uploaded to GitHub Security tab (discoverable in "Security" menu)
- Weekly baseline scan commits to `STAGE-4-CVE-BASELINE.md`
- Discord notification with severity breakdown

### 3. Manual Scanning

Run anytime to see current state:

```bash
# Full baseline scan (all services)
$ ./scripts/trivy-scan.sh

# Scan single image
$ trivy image ghcr.io/hotio/radarr:release

# Scan local dockerfile
$ trivy image --input Dockerfile
```

---

## Scanning Infrastructure

### File Structure

```
.
├── .github/workflows/
│   └── trivy-scan.yml              # GitHub Actions workflow
├── .trivy/
│   └── policy.yaml                 # Policy-as-code (severity levels)
├── scripts/
│   ├── trivy-scan.sh               # Baseline scan (all services)
│   ├── trivy-pre-commit.sh         # Pre-commit hook (blocks CRITICAL)
│   └── stage4-setup.sh             # Installation & setup
├── config/grafana/dashboards/
│   └── stage-4-cve-tracking.json   # CVE dashboard for Grafana
├── STAGE-4-CVE-BASELINE.md         # Scan report (regenerated weekly)
└── STAGE-4-REMEDIATION-PRIORITY.md # 4-week update plan
```

### Policy Configuration (.trivy/policy.yaml)

```yaml
policies:
  - CRITICAL CVEs → BLOCK (exit code 1)
  - HIGH CVEs → WARN (comment on PR, allows merge)
  - MEDIUM CVEs → INFO (logged, no block)
  - LOW CVEs → INFO (tracked in dashboard)

exceptions:
  # Add specific CVEs here if they're not exploitable in your context
  # Example: CVE-2024-12345 (not exploitable in read-only scenario)
```

---

## Remediation Plan (4-Week Schedule)

### Week 1-2: Critical Path Services

**Phase 1 Services:**
- grafana/promtail:2.5.0 (207 HIGH)
- grafana/grafana:10.0.0 (138 HIGH)
- grafana/loki:2.5.0 (98 HIGH)

**Expected Impact:** ~400 HIGH CVEs reduced (51% reduction)

**Process:**
1. Check Docker Hub/Quay for updates
2. Pull latest version locally
3. Get new digest: `docker inspect <image> | jq '.[] | .RepoDigests'`
4. Update docker-compose.yml with new digest
5. Test locally: `docker compose up -d <service>`
6. Verify scan: `./scripts/trivy-scan.sh`
7. Commit: `git commit -m "chore: update <service> (CVE remediation)"`

### Week 2-3: Import Pipeline

**Phase 2 Services:**
- ghcr.io/hotio/radarr:release (48 HIGH)
- ghcr.io/hotio/sonarr:release (7 HIGH)
- ghcr.io/hotio/prowlarr:release (48 HIGH)

**Expected Impact:** ~100 HIGH CVEs reduced

**Note:** Hotio maintains these actively; digests update weekly

### Week 3-4: Support Services

**Phase 3 Services:**
- golift/unpackerr (53 HIGH)
- ghcr.io/seerr-team/seerr (84 HIGH)
- ghcr.io/arabcoders/watchstate:latest (79 HIGH)

**Phase 4 Services (Low-risk):**
- nickfedor/watchtower:1.20.3 (10 HIGH)
- rclone/rclone:latest (8 HIGH)

**Expected Impact:** ~180 HIGH CVEs reduced

**Final Status:** ~20-30 HIGH CVEs remaining (~96% reduction)

---

## Integration with Phase 2

**Stage 1 ← → Stage 4 Parallel**

Stage 1 (Logging) provides visibility to debug issues.  
Stage 4 (Scanning) provides prevention of CVE-based attacks.

**Timeline:**
- **Week 1-2:** Stage 1 (Loki, Grafana) + Stage 4 (Trivy baseline) ✓ DONE
- **Week 2-4:** Stage 4 remediation (update images)
- **Week 3-4:** Stage 2 (Secrets) — use Stage 1 logs for troubleshooting
- **Week 5-8:** Stage 3 (Network) — requires Stage 1 visibility + Stage 2 secrets

---

## Access & Monitoring

### View Scan Results

**Local Files:**
- `STAGE-4-CVE-BASELINE.md` — Latest scan results
- `STAGE-4-REMEDIATION-PRIORITY.md` — 4-week update plan

**GitHub Security Tab:**
- URL: `https://github.com/YOUR_REPO/security/code-scanning`
- Shows SARIF results from CI/CD scans
- Automatically populated on every push/PR

**Grafana Dashboard (When Integrated):**
- Dashboard name: "Stage 4 - Image CVE Tracking"
- Requires manual import: `config/grafana/dashboards/stage-4-cve-tracking.json`
- Shows CVE trends, severity breakdown, services with most CVEs

### Manual Scan

```bash
# Run baseline scan anytime
./scripts/trivy-scan.sh

# Shows current state + updates STAGE-4-CVE-BASELINE.md
# Slow (5-10 min) but comprehensive
```

### Pre-commit Checks

```bash
# Automatic on every commit to docker-compose.yml
# Quick (~30 sec for modified images only)
# Blocks if CRITICAL CVEs found in staged images
```

---

## Policy Enforcement

### CRITICAL CVEs (0 found currently)

**Behavior:**
- Local: Pre-commit hook blocks commit
- GitHub: PR merge blocked, auto-close with error comment
- Expected action time: Immediate (within 24 hours)

**Example:**
```
❌ COMMIT BLOCKED: 1 CRITICAL CVE found

   Fix by:
   1. Identify affected image
   2. Find patched version on Docker Hub
   3. Update digest in docker-compose.yml
   4. Re-run trivy locally to verify
   5. Commit when clean

   Or skip: git commit --no-verify
```

### HIGH CVEs (780 found currently)

**Behavior:**
- Local: Pre-commit hook warns but allows
- GitHub: PR comment added, merge allowed
- Expected action time: Within 2 weeks

**Example:**
```
⚠️  WARNING: 207 HIGH CVEs found (commit allowed)

   Consider updating images to reduce CVEs
   Review: STAGE-4-REMEDIATION-PRIORITY.md
   Run: ./scripts/trivy-scan.sh
```

### MEDIUM/LOW CVEs

**Behavior:**
- Local: No warning
- GitHub: No comment
- Tracked in Grafana dashboard
- Expected action time: Quarterly review

---

## Known Limitations & Gotchas

### Trivy Limitations
- **Config scan only:** Trivy scans image metadata & known CVE databases
- **Not a full SAST:** Doesn't scan source code or compiled binaries for 0-days
- **CVE lag:** May be 1-2 days behind latest CVE announcements

### Docker Registry Limitations
- **Latest tag ambiguity:** `:latest` tag changes without notice
- **No guaranteed digest stability:** Rebuilds can change digest for same tag
- **Solution:** Always pin by digest, not tag

### High False-Positive Rate
- **Not all CVEs exploitable:** Many CVEs require specific conditions
- **Dependency-related:** Vulnerabilities in transitive deps you don't use
- **Solution:** Review exceptions carefully, don't blindly skip all HIGH

### Performance
- **Initial scan:** 5-10 minutes (all images, first time)
- **Incremental scan:** 30 seconds (only changed images)
- **GitHub Actions:** 2-3 minutes per run

---

## Troubleshooting

### Pre-commit Hook Not Running

```bash
# Check if hook is installed
ls -la .git/hooks/pre-commit

# Should be a symlink to scripts/trivy-pre-commit.sh
# If not: ln -sf ../../scripts/trivy-pre-commit.sh .git/hooks/pre-commit

# Test hook
git add docker-compose.yml
git commit -m "test" # Should run trivy check
```

### Trivy Not Found

```bash
# Check installation
which trivy
trivy version

# If not found, install manually
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh
sudo mv bin/trivy /usr/local/bin/
```

### GitHub Actions Not Running

```bash
# Verify workflow file exists
cat .github/workflows/trivy-scan.yml

# Check GitHub repo settings:
# Settings → Actions → Allow workflows to run (enable)

# Check GitHub secrets (if using Discord webhook):
# Settings → Secrets and variables → Actions → DISCORD_WEBHOOK_URL
```

### Scanner Getting Timeouts

```bash
# Trivy downloads CVE database on first run (large download)
# First scan may take 10+ minutes

# Speed up with offline DB:
trivy image --download-db-only
# Then subsequent scans are faster

# Cache location: ~/.cache/trivy/
```

---

## Next Steps

### Immediate (Today)

1. ✅ Baseline scan completed
2. ✅ Pre-commit hook installed
3. ✅ GitHub Actions workflow configured
4. ✅ Policy defined
5. **TODO:** Review `STAGE-4-REMEDIATION-PRIORITY.md`

### Week 1 (Remediation Phase 1)

1. Update Grafana Loki/Promtail/Grafana digests
2. Test locally: `docker compose up -d loki promtail grafana`
3. Verify logs still flowing: `curl http://localhost:3100/ready`
4. Run scan: `./scripts/trivy-scan.sh`
5. Commit changes

### Week 2-4 (Remediation Phases 2-4)

Follow the priority list in `STAGE-4-REMEDIATION-PRIORITY.md`:
- Phase 2: Update Radarr/Sonarr/Prowlarr
- Phase 3: Update Unpackerr/Seerr/WatchState
- Phase 4: Update Watchtower/Rclone

### Ongoing Monitoring

- Weekly: `./scripts/trivy-scan.sh` (automated via GitHub Actions)
- Quarterly: Full review + remediation plan update
- When updates available: Verify, test, update digest

---

## Related Documentation

- **Implementation:** `.claude/PHASE-2-ROADMAP.md` (Stage 4 full details)
- **Remediation plan:** `STAGE-4-REMEDIATION-PRIORITY.md` (4-week schedule)
- **Scan results:** `STAGE-4-CVE-BASELINE.md` (latest scan data)
- **Policy:** `.trivy/policy.yaml` (CVE blocking rules)
- **GitHub Actions:** `.github/workflows/trivy-scan.yml` (automated scanning)

---

## Architecture Diagram

```
Developer commits docker-compose.yml change
         ↓
[1] Pre-commit hook runs (local)
         ├─ trivy scan staged images (30 sec)
         ├─ Count CRITICAL/HIGH CVEs
         └─ If CRITICAL → ❌ BLOCK | If HIGH → ⚠️  WARN | Else → ✅ PASS
         ↓
Push to GitHub (if pre-commit passed)
         ↓
[2] GitHub Actions workflow (automated)
         ├─ Pull docker-compose.yml from PR
         ├─ Extract images
         ├─ trivy scan all images (2-3 min)
         ├─ Generate SARIF report
         ├─ Upload to Security tab
         ├─ Count CRITICAL CVEs
         └─ If CRITICAL → ❌ BLOCK MERGE | Else → ✅ ALLOW MERGE
         ↓
Weekly scheduled scan (always runs)
         ├─ Scan all images regardless of changes
         ├─ Update STAGE-4-CVE-BASELINE.md
         ├─ Commit to main
         └─ Post summary to Discord (HIGH/CRITICAL counts)
         ↓
Grafana dashboard (optional integration)
         └─ Display trends, severity breakdown, services with most CVEs
```

---

## Security Model

**Threat:** Deploying images with exploitable CVEs

**Prevention Strategy:**
1. **Pre-deployment detection** (Trivy scanning)
2. **Automated blocking** (CRITICAL CVEs block merge)
3. **Remediation tracking** (priority list + dashboard)
4. **Ongoing monitoring** (weekly rescans)

**Assumptions:**
- Image manifests are trustworthy (pinned by digest)
- CVE database is accurate (Trivy's CVE sources)
- CRITICAL/HIGH classification is meaningful (Aqua Security maintains)

**Out of scope:**
- 0-day vulnerabilities (not in CVE databases yet)
- Source code vulnerabilities (use SAST for that)
- Runtime exploits (requires dynamic analysis)

---

## Compliance & Auditing

### Audit Trail
- **Git history:** All image digest updates are committed
- **GitHub Actions:** All scans logged in workflow run history
- **Pre-commit:** Local scan results (if enabled in logging)
- **SARIF reports:** Archived in GitHub Security tab (90 days)

### Compliance Checklist
- ✅ CVE scanning on every commit to images (via pre-commit + GitHub Actions)
- ✅ CRITICAL CVEs blocked from deploying
- ✅ HIGH CVEs tracked and scheduled for remediation
- ✅ Audit trail available (git + GitHub)
- ✅ Policy-as-code (defined in .trivy/policy.yaml)

---

## Cost & Performance

- **Local scanning:** ~30 sec per commit (incremental)
- **Full baseline scan:** ~5-10 minutes (all images)
- **GitHub Actions:** ~2-3 minutes per push/PR
- **Storage:** CVE databases ~200MB (cached locally)
- **Cost:** $0 (Trivy free, aquasecurity.github.io/trivy/)

---

**Status:** ✓ STAGE 4 COMPLETE (INFRASTRUCTURE)  
**Ready for:** 4-week remediation sprint (starting Week 1-2)  
**Next major milestone:** Stage 2 (Secrets) after Phase 1 remediation done

---

**Last updated:** 2026-08-21  
**Deployment commit:** 0e648b7  
**Trivy version:** 0.74.0  
**Policy version:** 2024-01
