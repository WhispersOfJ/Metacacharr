/* Reference rail — open-a-service quicklinks, documentation (this
   stack's own README + each third-party app's real upstream docs, all
   verified against docker-compose.yml's actual images before being
   hardcoded here), and a read-only list of the Claude Code skills this
   project uses (dev-time only — this app has no mechanism to invoke
   them, so they're informational, not interactive). */
import { escapeHtml } from "./core.js";

const QUICK_LINKS = [
  { id: "plex", label: "Plex", port: 32400, path: "/web" },
  { id: "prowlarr", label: "Prowlarr", port: 9696 },
  { id: "radarr", label: "Radarr", port: 7878 },
  { id: "sonarr", label: "Sonarr", port: 8989 },
  { id: "nzbdav", label: "NzbDAV", port: 3000 },
  { id: "seerr", label: "Seerr", port: 5055 },
  { id: "cleanuparr", label: "Cleanuparr", port: 11011 },
  { id: "watchstate", label: "WatchState", port: 8705 },
];

export function buildQuickLinks() {
  const container = document.getElementById("quicklinks");
  container.innerHTML = QUICK_LINKS.map((svc) => {
    const url = `${location.protocol}//${location.hostname}:${svc.port}${svc.path || ""}`;
    return `<a class="quicklink" href="${url}" target="_blank" rel="noopener"><span class="dot unknown" id="qdot-${svc.id}"></span>${escapeHtml(svc.label)}</a>`;
  }).join("");
}

/* Each URL below was verified to resolve (github.com/<org>/<repo> or the
   project's own docs domain) against docker-compose.yml's real pinned
   image before being hardcoded — not guessed from the app's common name. */
const DOC_LINKS = [
  { app: "Radarr", desc: "movie root-folder/quality-profile management", urls: [["Wiki", "https://wiki.servarr.com/radarr"], ["Source", "https://github.com/Radarr/Radarr"]] },
  { app: "Sonarr", desc: "TV root-folder/quality-profile management", urls: [["Wiki", "https://wiki.servarr.com/sonarr"], ["Source", "https://github.com/Sonarr/Sonarr"]] },
  { app: "Prowlarr", desc: "indexer manager, syncs to Radarr/Sonarr", urls: [["Wiki", "https://wiki.servarr.com/prowlarr"], ["Source", "https://github.com/Prowlarr/Prowlarr"]] },
  { app: "NzbDAV", desc: "Usenet WebDAV server + SABnzbd-compatible API (nzbdav/nzbdav, a maintained super-fork of nzbdav-dev/nzbdav); FUSE-mounted for Plex/Radarr/Sonarr by the nzbdav_rclone sidecar", urls: [["Docs", "https://nzbdav.com/"], ["Source", "https://github.com/nzbdav/nzbdav"]] },
  { app: "Seerr", desc: "media request/discovery front-end", urls: [["Source", "https://github.com/seerr-team/seerr"]] },
  { app: "Plex", desc: "media server", urls: [["Support", "https://support.plex.tv"]] },
  { app: "Cleanuparr", desc: "queue strikes/malware-block/stalled cleanup", urls: [["Source", "https://github.com/Cleanuparr/Cleanuparr"]] },
  { app: "Unpackerr", desc: "RAR extraction for Radarr/Sonarr downloads", urls: [["Source", "https://github.com/Unpackerr/unpackerr"]] },
  { app: "Watchtower", desc: "container auto-update (maintained fork)", urls: [["Source", "https://github.com/nicholas-fedor/watchtower"]] },
];

export function buildDocLinks() {
  const wrap = document.getElementById("doc-links");

  const readmeRow = document.createElement("div");
  readmeRow.className = "rule-row";
  readmeRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">This stack's own README.md</span>
      <span class="rule-desc">No public downstream mirror exists for this repo — read directly off disk instead of linking out.</span>
    </div>
    <div class="rule-actions"><button class="btn-ghost" type="button" id="readme-open">Open</button></div>
  `;
  wrap.appendChild(readmeRow);
  document.getElementById("readme-open").addEventListener("click", async () => {
    const panel = document.getElementById("readme-panel");
    const body = document.getElementById("readme-body");
    panel.hidden = false;
    body.textContent = "Loading…";
    try {
      const res = await fetch("/api/docs/readme");
      const data = await res.json();
      body.textContent = res.ok ? data.text : (data?.detail?.message || "Could not load README.md");
    } catch (e) {
      body.textContent = e.message;
    }
  });
  document.getElementById("readme-close").addEventListener("click", () => {
    document.getElementById("readme-panel").hidden = true;
  });

  for (const doc of DOC_LINKS) {
    const row = document.createElement("div");
    row.className = "rule-row";
    row.innerHTML = `
      <div class="rule-main">
        <span class="rule-title">${escapeHtml(doc.app)}</span>
        <span class="rule-desc">${escapeHtml(doc.desc)}</span>
      </div>
      <div class="rule-actions">${doc.urls.map(([label, url]) => `<a class="doc-link-ext" href="${url}" target="_blank" rel="noopener">${escapeHtml(label)} ↗</a>`).join("")}</div>
    `;
    wrap.appendChild(row);
  }
}

/* Dev-time Claude Code skills this project uses — run inside Claude
   Code sessions, not inside this FastAPI app. Kept as a separate,
   read-only reference list rather than merged into the operator
   console above, since this app has no mechanism to invoke them. */
const CLAUDE_SKILLS = [
  { name: "docker-compose-manager", desc: "Start/stop/restart/inspect containers, mount-order aware." },
  { name: "health-monitor", desc: "Container health + HTTP-endpoint reachability sweep across the stack." },
  { name: "media-path-validator", desc: "Validate library/download paths are mounted and hardlink-capable." },
  { name: "request-manager-integrator", desc: "Wire Seerr to Radarr/Sonarr and verify the connection is live." },
  { name: "secret-injector", desc: "Generate/validate .env, rotate API keys, scan for leaked secrets." },
  { name: "arr-config-sync", desc: "Backup/restore/diff config across Radarr, Sonarr, Prowlarr." },
  { name: "trash-guides-applier", desc: "Apply TRaSH Guides quality profiles and custom formats." },
  { name: "usenet-orchestrator", desc: "Inspect/manage the Usenet download queue and health." },
  { name: "stack-cli-arr-fleet", desc: "Radarr/Sonarr queue, import, missing/cutoff, Bazarr subtitle ops." },
  { name: "stack-cli-discovery-import", desc: "Letterboxd/MDBList/Trakt/TMDb list imports and rating lookups." },
  { name: "stack-cli-infra-ops", desc: "Container control, backup verify/integrity, disk usage checks." },
  { name: "stack-cli-plex-kometa", desc: "Plex library/Butler tasks, duplicates, TMDb-link audit." },
  { name: "stack-cli-system-maintenance", desc: "Host package updates, reboot/disk/SMART/journal checks (terminal-only — see the Host rail's note above)." },
  { name: "stack-cli-usenet-queue", desc: "NzbDAV/Cleanuparr/Prowlarr status and queue ops." },
];

export function buildSkillsList() {
  const wrap = document.getElementById("skills-list");
  wrap.innerHTML = CLAUDE_SKILLS.map((s) => `
    <div class="rule-row">
      <div class="rule-main">
        <span class="skill-name">${escapeHtml(s.name)}</span>
        <span class="rule-desc">${escapeHtml(s.desc)}</span>
      </div>
    </div>`).join("");
}
