# Phase 2 Security Hardening Roadmap

**Status:** Planning (Phase 1 complete and deployed)  
**Timeline:** 6-12 weeks to full completion  
**Complexity:** Medium (4 independent stages, each 1-3 weeks)

---

## 4-Stage Comparison Matrix

| Aspect | Stage 1 (Logs) | Stage 2 (Secrets) | Stage 3 (Network) | Stage 4 (Scanning) |
|--------|---|---|---|---|
| **Goal** | Searchable logs + alerts | API keys in vault | Service isolation | CVE blocking |
| **Effort** | 1-2 weeks | 1-2 weeks | 2-3 weeks | 1 week |
| **Risk** | Low | Medium | Medium-High | Low |
| **ROI** | High (visibility) | High (security) | Medium (defense-in-depth) | High (prevention) |
| **External deps** | None (self-hosted) | None (Docker Swarm) | None | None (Trivy free) |
| **Testing needed** | Low | High | Very High | Low |
| **Reversible** | Yes (5 min) | Yes (30 min) | Yes (1-2 hours) | Yes (disable policy) |
| **Go-live recommendation** | 2-3 weeks | After Stage 1 | After Stage 2 | Anytime in parallel |

---

## Stage 1: Centralized Logging (Loki + Grafana)

**Why:** Local logs truncate at 30MB, hard to correlate errors, no alerting

**What you gain:**
- 30-day searchable log history
- Error trending dashboards
- SLA alerts (e.g., "service down >5m")
- Import failure tracking (Radarr/Sonarr)
- Auditable event logs

**Architecture:**
```
Docker → Promtail (collector) → Loki (storage) → Grafana (UI)
         ↓
      json-file logs (redundant fallback)
```

**Key services to add:**
1. **Loki** (log storage, 30-day retention, ~500MB disk/month)
2. **Promtail** (shipper, reads docker logs)
3. **Grafana** (search UI + dashboards + alerts)

**Implementation steps:**
1. Create Loki config (retention_period: 720h = 30 days)
2. Deploy Promtail to scrape docker logs
3. Add Loki data source to Grafana
4. Create dashboards for key services (nzbdav, Plex, Radarr/Sonarr)
5. Configure Discord alerts for errors/crashes

**Exit criteria:**
- ✓ Can search "ERROR" across all services
- ✓ Viewing 30-day log history works
- ✓ Alerts fire and post to Discord on errors

**Time: 1-2 weeks**

---

## Stage 2: Secrets Management (Docker Secrets)

**Why:** API keys in .env are plain text in git history, docker inspect, process listings

**What you gain:**
- Secrets never logged or exposed in docker inspect
- Secrets only in RAM during container runtime
- Audit trail for who accessed what
- Easier multi-machine deployments (Swarm stores secrets)

**What to move (priority order):**
```
Tier 1 (external auth):
  - PROWLARR_API_KEY
  - RADARR_API_KEY
  - SONARR_API_KEY
  - FRONTEND_BACKEND_API_KEY (NzbDAV)
  - PLEX_TOKEN
  - WS_API_KEY

Tier 2 (internal services):
  - NZBDAV_WEBDAV_USER / _PASS
  - NZBDAV_USENET_USER / _PASS
  - NZBDAV_RCLONE_RC_PASS

Tier 3 (control panel):
  - CONTROL_PANEL_SECRET_KEY
  - CONTROL_PANEL_ADMIN_PASSWORD
```

**Implementation:**
```bash
# One-time setup
docker swarm init

# Create secrets from .env
echo "$PROWLARR_API_KEY" | docker secret create prowlarr_api_key -
echo "$RADARR_API_KEY" | docker secret create radarr_api_key -
# ... repeat for all 15+ secrets

# Update compose (Swarm syntax)
services:
  control-panel:
    secrets:
      - prowlarr_api_key
      - radarr_api_key
    environment:
      PROWLARR_API_KEY_FILE: /run/secrets/prowlarr_api_key
```

**Exit criteria:**
- ✓ No secrets in `git log --all -S PROWLARR_API_KEY`
- ✓ `docker inspect control-panel` shows no env vars with secrets
- ✓ All services authenticating via /run/secrets mount
- ✓ Old .env secrets deleted

**Time: 1-2 weeks (includes testing all auth paths)**

---

## Stage 3: Network Segmentation

**Why:** Plex on same network as NzbDAV (if Plex is compromised, API keys exposed)

**Current risk:**
```
Plex ← → Radarr ← → NzbDAV (API key vulnerable to Plex exploit)
 ↑         ↑
All on stacknet, no isolation
```

**Target architecture:**
```
PUBLIC:    Plex, Seerr, Control Panel
           ↓ (Control Panel bridges all)
INTERNAL:  Radarr, Sonarr, Prowlarr
           ↓ (internal-only access)
SECRETS:   NzbDAV, Rclone FUSE
```

**Implementation:**
```yaml
networks:
  public:
    name: stacknet-public
  internal:
    name: stacknet-internal
    internal: true  # No outbound to host
  secrets:
    name: stacknet-secrets
    internal: true

services:
  plex:
    networks: [public]  # No direct access to NzbDAV
  
  radarr:
    networks: [internal, secrets]  # Only internal/secret tiers
  
  control-panel:
    networks: [public, internal, secrets]  # Bridges all (privileged)
```

**Exit criteria:**
- ✓ `docker exec plex curl http://nzbdav:3000` fails (no route)
- ✓ `docker exec control-panel curl http://nzbdav:3000` succeeds
- ✓ `docker exec radarr curl http://nzbdav:3000` succeeds
- ✓ Plex→Radarr still works (via Control Panel API)

**Challenges:**
- Plex uses network_mode: host (needs special handling)
- Extensive testing required (multiple interconnected APIs)
- Potential breakage if assumptions wrong

**Time: 2-3 weeks (1w implementation + 1w testing + 1w troubleshooting)**

---

## Stage 4: Image Vulnerability Scanning (Trivy)

**Why:** Digest pinning only prevents tag hijacking; doesn't catch CVEs in pinned digests

**What you gain:**
- Automated SCA on every pull request
- Weekly scans to detect new CVEs in pinned images
- Blocks merge if CRITICAL CVE found
- Compliance audit trail

**Tool: Trivy (Aqua Security)**
- Fast, no external API needed
- Policy-as-code (skip low/medium, block critical)
- Free, Apache 2.0

**Implementation:**
```yaml
# GitHub Actions (if using GitHub)
name: Image Security Scan
on: [pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'config'
          scan-ref: 'docker-compose.yml'
          severity: 'CRITICAL'  # Only block critical
          exit-code: '1'
```

**Or locally (pre-commit hook):**
```bash
#!/bin/bash
trivy image --severity CRITICAL ghcr.io/hotio/radarr:release || exit 1
trivy image --severity CRITICAL ghcr.io/hotio/sonarr:release || exit 1
# ... etc
```

**Exit criteria:**
- ✓ CI/CD blocks merge if CRITICAL CVE in any image
- ✓ Weekly scan runs and posts results to Discord
- ✓ Team aware of policy (CRITICAL blocks, HIGH/MEDIUM notifies)

**Time: 1 week (mostly setup + policy tuning)**

---

## Recommended Sequencing

### Fast Track (Aggressive, 6-8 weeks)
```
Week 1-2:  Stage 1 (Logs) + Stage 4 (Scanning) in parallel
           ↓ (low-risk, non-blocking)
Week 3-4:  Stage 2 (Secrets)
           ↓ (wait for Logs to debug auth)
Week 5-8:  Stage 3 (Network)
           ↓ (requires most testing)
```

**Pros:** Fast to full hardening  
**Cons:** Parallel work on 1+4, requires coordination

### Conservative Track (Safer, 10-12 weeks)
```
Week 1-2:  Stage 1 (Logs) - establish visibility first
Week 3-4:  Stage 4 (Scanning) - add automated prevention
Week 5-6:  Stage 2 (Secrets) - now you have logs to debug
Week 7-12: Stage 3 (Network) - most testing, no surprises
```

**Pros:** Sequential, easier to debug each stage  
**Cons:** Slower to full hardening, more manual testing

**Recommendation:** Fast track. Stages 1+4 are low-risk and can run in parallel. Stages 2+3 wait for 1 (logging helps troubleshoot).

---

## Decision Checklist

Before starting Phase 2, decide:

- [ ] **Stage 1 (Logs):** Do you want real-time error alerts or just searchable logs?
- [ ] **Stage 2 (Secrets):** Is multi-machine secret sync needed, or single-host Docker Swarm sufficient?
- [ ] **Stage 3 (Network):** Is Plex compromise a realistic threat in your threat model?
- [ ] **Stage 4 (Scanning):** Should CRITICAL CVEs auto-block merge, or just notify?

---

## Known Gotchas

### Stage 1 (Logs)
- Loki retention is time-based, not size-based (50GB cache fills regardless of age)
- Promtail needs docker.sock read access (run as root or special group)
- Grafana dashboards don't auto-export (save as JSON if you need backup)

### Stage 2 (Secrets)
- Docker Secrets only work in Swarm mode (minor overhead, no real Swarm features used)
- Rotating a secret requires recreate (can't change secret in-place)
- Old .env entries must be manually deleted (script doesn't do it for safety)

### Stage 3 (Network)
- Plex on network_mode: host bypasses all Docker network isolation (needs iptables rules instead)
- Moving services between networks requires testing every API path
- health-check cross-network dependencies can timeout during discovery

### Stage 4 (Scanning)
- Trivy scans image *config*, not actual CVEs in binaries (use Grype for deeper scans)
- Policy too strict blocks legitimate dev releases
- No auto-remediation (only blocks merge, doesn't auto-update image)

---

## Success Metrics

| Stage | Metric | Target | How to verify |
|-------|--------|--------|---|
| 1 | Log retention | 30 days searchable | Query old date range in Grafana |
| 2 | Secret exposure | 0 in git/docker inspect | `git log -S SECRET`, `docker inspect` |
| 3 | Network isolation | Plex ↛ NzbDAV | `docker exec plex curl nzbdav:3000` fails |
| 4 | Scanning enforcement | CRITICAL blocks merge | PR with CRITICAL CVE can't merge |

---

## Rollback Procedures

**Stage 1 (Logs):** Delete Loki/Grafana/Promtail, revert compose to json-file (5 min)

**Stage 2 (Secrets):** `docker secret rm *`, revert compose to env vars (30 min)

**Stage 3 (Network):** Merge networks back to single `stacknet`, recreate all services (1-2 hours)

**Stage 4 (Scanning):** Disable Trivy in CI/CD, update policy to only warn (10 min)

---

## Cost Estimate

- **Stage 1 (Logs):** ~$0 self-hosted, 500MB disk/month
- **Stage 2 (Secrets):** ~$0 self-hosted, negligible resources
- **Stage 3 (Network):** ~$0 self-hosted, configuration only
- **Stage 4 (Scanning):** ~$0 self-hosted (Trivy free)

**Total:** No CapEx, mainly engineering time (50-100 hours for full implementation)

---

## Next Action

1. **Today:** Decide which stage to start with (recommend Stage 1)
2. **This week:** Read detailed implementation guide (to be created)
3. **Next week:** Begin Stage 1 + Stage 4 (parallel)

Which stage are you most interested in starting with?

- **Stage 1 (Logs):** Best for debugging and visibility
- **Stage 2 (Secrets):** Best for compliance and security
- **Stage 3 (Network):** Best for defense-in-depth
- **Stage 4 (Scanning):** Best for prevention (recommend doing early)
