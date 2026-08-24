/* Overview rail: rapid actions. */
import { escapeHtml, postAction, setStatusLine } from "./core.js";
import { logLine } from "./activity-log.js";

const PRIMARY_ACTIONS = [
  { id: "plex-scan", title: "Scan for new files", desc: "Refresh every Plex library section.", endpoint: "/api/plex/scan", icon: "search" },
  { id: "plex-empty-trash", title: "Empty trash", desc: "Permanently remove already-deleted items across every library.", endpoint: "/api/plex/empty-trash", icon: "trash" },
  { id: "plex-optimize-db", title: "Optimize database", desc: "Clears bloat after large library changes.", endpoint: "/api/plex/optimize-db", icon: "database" },
  { id: "plex-clean-bundles", title: "Clean old bundles", desc: "Remove metadata bundles Plex no longer needs.", endpoint: "/api/plex/clean-bundles", icon: "broom" },
];

export function buildPrimaryActions() {
  const wrap = document.getElementById("primary-actions");
  for (const action of PRIMARY_ACTIONS) {
    const row = document.createElement("div");
    row.className = "rule-row";
    row.innerHTML = `
      <div class="rule-main">
        <span class="rule-title">${escapeHtml(action.title)}</span>
        <span class="rule-desc">${escapeHtml(action.desc)}</span>
      </div>
      <div class="rule-actions">
        <button class="btn-primary" type="button">Run</button>
      </div>
      <div class="rule-status" id="status-${action.id}">—</div>
    `;
    wrap.appendChild(row);
    const btn = row.querySelector("button");
    const status = row.querySelector(".rule-status");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      setStatusLine(status, "pending", "Running…");
      logLine("pending", `${action.title} — requested`);
      try {
        const data = await postAction(action.endpoint);
        setStatusLine(status, "success", data.message);
        logLine("ok", `${action.title} — ${data.message}`);
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `${action.title} — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  }
}
