/* Host rail — two lanes plus a live resource strip. Vitals are read-only
   checks this container can genuinely answer from its own mounts
   (docker.sock, /host-config, /mnt, and - since 2026-07-26's Plex Health
   mount - /host-proc for real host-wide CPU/RAM). Reboot/pacman sync/
   pacman upgrade are real host-changing actions,
   brokered through the optional controlpanel-helper daemon (see
   core/host_helper_client.py and
   .claude/plans/host-privileged-helper.plan.md) - this container never
   gets a privileged path to the host directly, only three fixed verbs
   through that daemon's Unix socket. */
import { escapeHtml, postAction, setStatusLine } from "./core.js";
import { logLine } from "./activity-log.js";
import { fetchAndRender } from "./result-render.js";
import { armButton } from "./buttons.js";
import { refreshStatus } from "./status.js";
import { renderSparkline, pushHistory } from "./sparkline.js";

const HOST_VITALS = [
  { id: "mount-health", label: "Mount health", desc: "Every known FUSE mountpoint under /mnt, checked for a clean listing.", path: "/api/mount-health" },
  { id: "oom-check", label: "OOM kills", desc: "Containers Docker has ever recorded an OOM-kill flag for.", path: "/api/oom-check" },
  { id: "resource-check", label: "Resource limits", desc: "Containers missing an explicit mem_limit or cpus.", path: "/api/resource-check" },
  { id: "disk-usage", label: "Config disk usage", desc: "Per-app config/ directory size, largest first.", path: "/api/disk-usage" },
  { id: "disk-health", label: "Disk health", desc: "Host mount free space plus reclaimable space from unused Docker images/volumes/build cache.", path: "/api/disk-health" },
];

export function buildHostVitals() {
  const wrap = document.getElementById("host-vitals");
  for (const v of HOST_VITALS) {
    const row = document.createElement("div");
    row.className = "rule-row";
    row.innerHTML = `
      <div class="rule-main">
        <span class="rule-title">${escapeHtml(v.label)}</span>
        <span class="rule-desc">${escapeHtml(v.desc)}</span>
      </div>
      <div class="rule-actions"><button class="btn-ghost" type="button">Check</button></div>
      <div class="rule-result" hidden></div>
    `;
    wrap.appendChild(row);
    const btn = row.querySelector("button");
    const result = row.querySelector(".rule-result");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      logLine("pending", `${v.label} — requested`);
      try {
        await fetchAndRender(result, v.method || "GET", v.path);
        logLine("ok", `${v.label} — loaded`);
      } catch (e) {
        logLine("err", `${v.label} — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  }
}

export function buildHostActions() {
  const wrap = document.getElementById("host-actions");

  const restartRow = document.createElement("div");
  restartRow.className = "rule-row";
  restartRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">Restart entire stack</span>
      <span class="rule-desc">Restarts every container except this panel, mount-order aware. Brief outage stack-wide.</span>
    </div>
    <div class="rule-actions"><button class="btn-danger" type="button">Restart everything</button></div>
    <div class="rule-status" id="status-restart-all">—</div>
  `;
  wrap.appendChild(restartRow);
  const restartBtn = restartRow.querySelector("button");
  const restartStatus = restartRow.querySelector(".rule-status");
  armButton(restartBtn, "Restart everything", "Click again to confirm", async () => {
    restartBtn.disabled = true;
    setStatusLine(restartStatus, "pending", "Restarting…");
    logLine("pending", "Restart entire stack — requested");
    try {
      const data = await postAction("/api/stack/restart-all");
      setStatusLine(restartStatus, "success", data.message);
      logLine("ok", `Restart entire stack — ${data.message}`);
      refreshStatus();
    } catch (e) {
      setStatusLine(restartStatus, "error", e.message);
      logLine("err", `Restart entire stack — ${e.message}`);
    } finally {
      restartBtn.disabled = false;
    }
  });

  const pruneRow = document.createElement("div");
  pruneRow.className = "rule-row";
  pruneRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">Prune unused Docker space</span>
      <span class="rule-desc">Dangling images and zero-refcount volumes only - never a running or stopped-but-referenced container's own image/volume.</span>
    </div>
    <div class="rule-actions"><button class="btn-ghost" type="button">Prune</button></div>
    <div class="rule-status" id="status-disk-prune">—</div>
  `;
  wrap.appendChild(pruneRow);
  const pruneBtn = pruneRow.querySelector("button");
  const pruneStatus = pruneRow.querySelector(".rule-status");
  armButton(pruneBtn, "Prune", "Click again to confirm", async () => {
    pruneBtn.disabled = true;
    setStatusLine(pruneStatus, "pending", "Pruning…");
    logLine("pending", "Disk prune — requested");
    try {
      const data = await postAction("/api/disk-health/prune", { confirm: true });
      setStatusLine(pruneStatus, "success", data.message);
      logLine("ok", `Disk prune — ${data.message}`);
    } catch (e) {
      setStatusLine(pruneStatus, "error", e.message);
      logLine("err", `Disk prune — ${e.message}`);
    } finally {
      pruneBtn.disabled = false;
    }
  });

  const hostActionRow = (title, desc, path, idleLabel, statusId, danger) => {
    const row = document.createElement("div");
    row.className = "rule-row";
    row.innerHTML = `
      <div class="rule-main">
        <span class="rule-title">${escapeHtml(title)}</span>
        <span class="rule-desc">${escapeHtml(desc)}</span>
      </div>
      <div class="rule-actions"><button class="${danger ? "btn-danger" : "btn-ghost"}" type="button">${escapeHtml(idleLabel)}</button></div>
      <div class="rule-status" id="${statusId}">—</div>
    `;
    wrap.appendChild(row);
    const btn = row.querySelector("button");
    const status = row.querySelector(".rule-status");
    armButton(btn, idleLabel, "Click again to confirm", async () => {
      btn.disabled = true;
      setStatusLine(status, "pending", "Running…");
      logLine("pending", `${title} — requested`);
      try {
        const data = await postAction(path, { confirm: true });
        setStatusLine(status, "success", data.message);
        logLine("ok", `${title} — ${data.message}`);
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `${title} — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  };

  hostActionRow(
    "Sync package database",
    "Refreshes pacman's package database only — no packages are installed or changed. Requires the host-side helper daemon (see scripts/host-helper/README.md).",
    "/api/host/pacman-sync", "Sync", "status-pacman-sync", false,
  );
  hostActionRow(
    "Upgrade packages",
    "Runs a full host system upgrade (pacman -Syu) — can take a while and may need a reboot afterward. Requires the host-side helper daemon.",
    "/api/host/pacman-upgrade", "Upgrade", "status-pacman-upgrade", true,
  );
  hostActionRow(
    "Reboot host",
    "Reboots the physical machine this entire stack runs on — every container, including this panel, goes down and back up. Requires the host-side helper daemon.",
    "/api/host/reboot", "Reboot", "status-host-reboot", true,
  );
}

/* Live resource strip - polls /api/host-resources every 5s and keeps a
   short rolling buffer per metric to draw as an inline sparkline. Plain
   polling, not SSE: this is a point-in-time gauge refreshing on a fixed
   cadence, not a long-running background job streaming progress - SSE
   earns its keep for poster-sync's kind of job, not this one. */
const RESOURCE_HISTORY_LEN = 24;
const cpuHistory = [];
const memHistory = [];

export function buildHostResources() {
  const wrap = document.getElementById("host-resources");
  if (!wrap) return;
  wrap.innerHTML = `
    <div class="sparkline-row">
      <div class="sparkline-block">
        <span class="sparkline-label">CPU <b id="host-cpu-val">—</b></span>
        <svg class="sparkline" viewBox="0 0 200 40" preserveAspectRatio="none"></svg>
      </div>
      <div class="sparkline-block sparkline-ram">
        <span class="sparkline-label">RAM <b id="host-ram-val">—</b></span>
        <svg class="sparkline" viewBox="0 0 200 40" preserveAspectRatio="none"></svg>
      </div>
    </div>
    <p class="hint" id="host-resources-hint"></p>
  `;
}

export async function refreshHostResources() {
  const wrap = document.getElementById("host-resources");
  if (!wrap || wrap.innerHTML === "") return;
  try {
    const res = await fetch("/api/host-resources");
    if (res.status === 503) {
      document.getElementById("host-resources-hint").textContent = "Host /proc mount not available.";
      return;
    }
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    const data = await res.json();
    pushHistory(cpuHistory, data.cpu_percent, RESOURCE_HISTORY_LEN);
    pushHistory(memHistory, data.mem_percent, RESOURCE_HISTORY_LEN);
    document.getElementById("host-cpu-val").textContent = `${data.cpu_percent}%`;
    document.getElementById("host-ram-val").textContent = `${data.mem_percent}%`;
    document.getElementById("host-resources-hint").textContent = `${data.mem_used} / ${data.mem_total} RAM`;
    renderSparkline(wrap.querySelector(".sparkline-block:not(.sparkline-ram) svg"), cpuHistory); // CPU: defaults (violet, no fill)
    renderSparkline(wrap.querySelector(".sparkline-ram svg"), memHistory, { stroke: "var(--good)", fill: true });
  } catch (e) {
    logLine("err", `Host resources — ${e.message}`);
  }
}
