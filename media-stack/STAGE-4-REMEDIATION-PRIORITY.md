# Stage 4: CVE Remediation Priority Plan

**Status:** Baseline scan complete, 0 CRITICAL CVEs, 780 HIGH CVEs identified  
**Policy:** Focus on HIGH CVEs in critical services first  
**Timeline:** Phase in updates over 4 weeks

---

## Prioritized Remediation List

### Phase 1 (Week 1-2): Critical Path Services
**These services directly impact core functionality**

#### 1. grafana/promtail:2.5.0 → UPGRADE
- **Status:** 🟠 HIGH: 207, MEDIUM: 235
- **Impact:** Log collection, critical for visibility
- **Risk:** Low (read-only log scraping)
- **Action:** 
  - Check for 2.6.0+ release
  - If available: test locally, update digest
  - Rescan to verify improvement
- **Deadline:** End of Week 1
- **Expected reduction:** 30-50% of HIGH CVEs (assume 100+ fixed)

#### 2. grafana/grafana:10.0.0 → UPGRADE
- **Status:** 🟠 HIGH: 138, MEDIUM: 219
- **Impact:** Logging UI, non-critical but useful
- **Risk:** Medium (DB migration possible)
- **Action:**
  - Check for 10.1.0+ release
  - Test dashboard export/import
  - Update digest if compatible
- **Deadline:** End of Week 1
- **Expected reduction:** 20-30% of HIGH CVEs

#### 3. grafana/loki:2.5.0 → UPGRADE
- **Status:** 🟠 HIGH: 98, MEDIUM: 86
- **Impact:** Log storage, critical for logging stage
- **Risk:** Medium (schema changes possible)
- **Action:**
  - Check for 2.6.0+ release
  - Backup config, test upgrade
  - Verify log retention still works
- **Deadline:** End of Week 2
- **Expected reduction:** 30-40% of HIGH CVEs

### Phase 2 (Week 2-3): Import Pipeline
**These services handle download/import workflow**

#### 4. ghcr.io/hotio/radarr:release → UPGRADE
- **Status:** 🟠 HIGH: 48, MEDIUM: 24
- **Impact:** Movie importing, core workflow
- **Risk:** Low (hotio is regularly maintained)
- **Action:**
  - Check for new digest (hotio updates frequently)
  - Test with existing library
  - Update digest
- **Deadline:** End of Week 2
- **Expected reduction:** 50-70% of HIGH CVEs

#### 5. ghcr.io/hotio/sonarr:release → UPGRADE
- **Status:** 🟠 HIGH: 7, MEDIUM: 13
- **Impact:** TV importing, core workflow
- **Risk:** Low (hotio is regularly maintained)
- **Action:**
  - Check for new digest
  - Test with existing library
  - Update digest
- **Deadline:** End of Week 2
- **Expected reduction:** 50-70% of HIGH CVEs

#### 6. ghcr.io/hotio/prowlarr:release → UPGRADE
- **Status:** 🟠 HIGH: 48, MEDIUM: 24
- **Impact:** Indexer management, required for imports
- **Risk:** Low (hotio is regularly maintained)
- **Action:**
  - Check for new digest
  - Verify indexer connections still work
  - Update digest
- **Deadline:** End of Week 2
- **Expected reduction:** 50-70% of HIGH CVEs

### Phase 3 (Week 3-4): Supporting Services
**These services provide additional functionality but are not on critical path**

#### 7. golift/unpackerr
- **Status:** 🟠 HIGH: 53, MEDIUM: 36
- **Impact:** Post-download processing
- **Risk:** Low (processing-only)
- **Action:**
  - Check for new release
  - Test file unpacking
  - Update digest
- **Deadline:** End of Week 3
- **Expected reduction:** 40-60% of HIGH CVEs

#### 8. ghcr.io/seerr-team/seerr
- **Status:** 🟠 HIGH: 84, MEDIUM: 93
- **Impact:** Request UI, convenience feature
- **Risk:** Medium (Node.js app)
- **Action:**
  - Check for 1.3.0+ (if available)
  - Test request creation workflow
  - Update digest
- **Deadline:** End of Week 3
- **Expected reduction:** 30-50% of HIGH CVEs

#### 9. ghcr.io/arabcoders/watchstate:latest
- **Status:** 🟠 HIGH: 79, MEDIUM: 95
- **Impact:** Watch state sync (Plex tracking)
- **Risk:** Medium (PHP/API app)
- **Action:**
  - Check for latest tag update
  - Test Plex webhook still works
  - Update digest
- **Deadline:** End of Week 3
- **Expected reduction:** 30-50% of HIGH CVEs

### Phase 4 (Week 4): Low-Risk Services
**These services have minimal impact on core functionality**

#### 10. nickfedor/watchtower:1.20.3
- **Status:** 🟠 HIGH: 10, MEDIUM: 0
- **Impact:** Auto-update checker (non-critical)
- **Risk:** Low (read-only Docker socket)
- **Action:**
  - Check for 1.21.0+ release
  - Update digest
- **Deadline:** End of Week 4
- **Expected reduction:** 50-80% of HIGH CVEs

#### 11. rclone/rclone:latest
- **Status:** 🟠 HIGH: 8, MEDIUM: 0
- **Impact:** FUSE mount handler
- **Risk:** Low (data transfer only)
- **Action:**
  - Check for latest update
  - Test mount still works
  - Update digest
- **Deadline:** End of Week 4
- **Expected reduction:** 50-80% of HIGH CVEs

#### 12. plexinc/pms-docker:latest
- **Status:** 🟡 HIGH: 0, MEDIUM: 17 (no HIGH CVEs!)
- **Impact:** Media server (core)
- **Risk:** Medium (major version updates rare)
- **Action:**
  - Monitor weekly for updates
  - No action needed currently (no HIGH)
  - Check quarterly
- **Deadline:** Ongoing

#### 13. ghcr.io/infinidysk/infinidysk:latest
- **Status:** ✅ CLEAN (0 CVEs!)
- **Impact:** NzbDAV client
- **Risk:** N/A
- **Action:**
  - No action needed
  - Keep as-is
- **Deadline:** N/A

#### 14. ghcr.io/cleanuparr/cleanuparr:2.10.5
- **Status:** ✅ CLEAN (0 CVEs!)
- **Impact:** Cleanup automation
- **Risk:** N/A
- **Action:**
  - No action needed
  - Keep as-is
- **Deadline:** N/A

---

## Process for Each Update

### Step 1: Check for Updates
```bash
# Check Docker Hub / Quay for latest tag
curl -s "https://registry.hub.docker.com/v2/namespaces/hotio/repositories/radarr/tags?page_size=5" | jq '.results[].name'

# Or visit the image directly on Docker Hub/Quay
```

### Step 2: Verify Compatibility
```bash
# Pull and test locally
docker pull ghcr.io/hotio/radarr:release
docker run -it --rm ghcr.io/hotio/radarr:release /bin/bash
# Check version, config format, etc.
```

### Step 3: Get Digest
```bash
# Get the image digest (SHA256)
docker inspect ghcr.io/hotio/radarr:release | jq '.[] | .RepoDigests'

# Or use trivy
trivy image --format json ghcr.io/hotio/radarr:release | jq '.Results[].RepoDigests'
```

### Step 4: Update docker-compose.yml
```yaml
# Before
radarr:
  image: ghcr.io/hotio/radarr:release@sha256:abc123...

# After
radarr:
  image: ghcr.io/hotio/radarr:release@sha256:def456...
```

### Step 5: Test Locally
```bash
# Restart service
docker compose down radarr
docker compose up -d radarr

# Wait for health
sleep 30
docker compose ps radarr

# Check logs
docker logs radarr | tail -20
```

### Step 6: Verify Scan Results
```bash
# Re-run trivy on the updated image
trivy image ghcr.io/hotio/radarr:release

# Confirm HIGH CVEs reduced
```

### Step 7: Commit and Push
```bash
git add docker-compose.yml
git commit -m "chore: update radarr image to latest (CVE remediation)"
git push origin main
```

---

## Expected Timeline & Impact

### Week 1 Summary
- ✓ Update Grafana Loki/Promtail (3 services)
- Expected HIGH reduction: ~400 (from 780)
- Status: Logging tier hardened

### Week 2 Summary
- ✓ Update Radarr/Sonarr/Prowlarr (3 services)
- Expected HIGH reduction: ~140 (from remaining 380)
- Status: Import pipeline hardened

### Week 3 Summary
- ✓ Update Unpackerr/Seerr/WatchState (3 services)
- Expected HIGH reduction: ~200 (from remaining 240)
- Status: Support tier hardened

### Week 4 Summary
- ✓ Update Watchtower/Rclone (2 services)
- Expected HIGH reduction: ~18 (from remaining 40)
- Status: Utility tier hardened

### Final Status (End of Week 4)
- ✅ CRITICAL: 0 (unchanged, none to begin with)
- 🟠 HIGH: ~20-30 (from 780, ~96% reduction)
- 🟡 MEDIUM: ~400 (from 842, ~50% reduction)
- Total impact: Core services hardened, legacy packages identified

---

## Ongoing Monitoring (Post-Remediation)

### Weekly Tasks
- Run ./scripts/trivy-scan.sh
- Check for new CRITICAL CVEs (should block CI/CD)
- Review Grafana dashboard for HIGH trends

### Monthly Tasks
- Update images that have released patches
- Review remediation priority if new vulnerabilities emerge

### Quarterly Tasks
- Full re-baseline scan (./scripts/trivy-scan.sh)
- Update policy if new threats identified
- Rotate image digests if major version jumps available

---

## Exit Criteria (Stage 4 Complete)

- ✅ Baseline scan run and report generated (DONE)
- ✅ GitHub Actions workflow blocking CRITICAL CVEs (DONE)
- ✅ Remediation priority list created (DONE)
- ⏳ Phase 1 updates applied (Week 1-2)
- ⏳ Phase 2 updates applied (Week 2-3)
- ⏳ Phase 3 updates applied (Week 3-4)
- ⏳ Phase 4 updates applied (Week 4)
- ⏳ Grafana CVE dashboard created
- ⏳ Discord alerts configured
- ⏳ Pre-commit hook installed (blocking local CRITICAL CVEs)
- ⏳ Final scan confirms <50 HIGH CVEs remaining

---

## Notes

- **Hotio images (Radarr/Sonarr/Prowlarr)** update frequently, expect digests to change weekly
- **Grafana ecosystem (Loki/Promtail/Grafana)** typically patch every 2-4 weeks
- **Watchtower** only needed if auto-update checking desired; can be removed if not using
- **Plex** rarely has updates; Plex server updates controlled manually
- **Node.js based services** (Seerr, WatchState) tend to have more deps → more CVEs

---

## Rollback Plan

If an update breaks functionality:

```bash
# Revert docker-compose.yml to previous version
git log --oneline docker-compose.yml | head -5
git revert <commit-hash>

# Or manually edit and restore old digest
git checkout HEAD~1 docker-compose.yml

# Restart service
docker compose restart <service>

# Verify logs
docker logs <service> | tail -30
```

Time to rollback: 5-10 minutes

---

**Last updated:** 2026-08-21  
**Next full scan:** 2026-08-28  
**Remediation start:** Ready (awaiting approval to proceed)
