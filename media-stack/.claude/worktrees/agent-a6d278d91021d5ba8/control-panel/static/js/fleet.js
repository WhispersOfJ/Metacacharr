/* Fleet rail: every container, live from Docker, grouped by subsystem
   (Source selection — option B). Never a hardcoded allow-list: a
   service missing from FLEET_GROUPS just falls into "Other" rather
   than being hidden, matching app.py's own CONTAINER_LABELS staleness
   tolerance. Clicking a row (not its action buttons) makes it the
   active log-console source. */
import { escapeHtml, svg, postAction } from "./core.js";
import { logLine, selectLogSource, getActiveLogName } from "./activity-log.js";
import { armIconButton } from "./buttons.js";
import { renderStatusDots } from "./status.js";
import { renderSparkline, pushHistory } from "./sparkline.js";

const FLEET_GROUPS = {
  prowlarr: "Indexing", radarr: "Arr apps", sonarr: "Arr apps",
  nzbdav: "Usenet", nzbdav_rclone: "Usenet", seerr: "Requests", plex: "Media server",
  unpackerr: "Post-processing", watchtower: "Auto-updates",
  cleanuparr: "Queue cleanup",
  "control-panel": "Dashboard",
  watchstate: "Discovery",
};
const GROUP_ORDER = ["Arr apps", "Indexing", "Usenet", "Requests", "Media server", "Subtitles", "Queue cleanup", "Library maintenance", "Discovery", "Post-processing", "Auto-updates", "Dashboard", "Other"];
// localStorage isn't a real store under plain `node --test` (no DOM) - Node
// exposes the identifier but throws on access. Guard so fleet.test.js can
// import groupHistoryFor without a browser environment. No behavior change
// in the browser, where localStorage always works.
function readCollapsedGroups() {
  try {
    return JSON.parse(localStorage.getItem("fleetCollapsed") || "[]");
  } catch {
    return [];
  }
}
const collapsedGroups = new Set(readCollapsedGroups());

const FLEET_HISTORY_LEN = 24; // matches Host's RESOURCE_HISTORY_LEN
const containerHistory = new Map(); // name -> { cpu: number[], mem: number[] }

// Exported for fleet.test.js; also used internally to key per-container and
// per-group (via a "__group__" prefixed name) CPU/mem sample buffers.
export function groupHistoryFor(name) {
  if (!containerHistory.has(name)) {
    containerHistory.set(name, { cpu: [], mem: [] });
  }
  return containerHistory.get(name);
}

function fmtPercent(v) { return v === null || v === undefined ? "—" : `${v.toFixed(1)}%`; }
function fmtMb(v) {
  if (v === null || v === undefined) return "—";
  return v >= 1024 ? `${(v / 1024).toFixed(2)} GB` : `${v.toFixed(0)} MB`;
}

function fleetRowHtml(c) {
  const stateClass = c.state === "running" ? (c.health === "unhealthy" ? "down" : c.health === "starting" ? "unknown" : "up") : c.state === "exited" || c.state === "created" ? "down" : "unknown";
  const healthLabel = c.state !== "running" ? c.state : c.health ? c.health : "running";
  const cpuPct = c.cpu_percent === null || c.cpu_percent === undefined ? 0 : Math.min(c.cpu_percent, 100);
  const memPct = c.mem_percent === null || c.mem_percent === undefined ? 0 : Math.min(c.mem_percent, 100);
  const cpuCls = cpuPct >= 90 ? "bad" : cpuPct >= 70 ? "warn" : "";
  const memCls = memPct >= 90 ? "bad" : memPct >= 70 ? "warn" : "";
  return `
    <div class="rule-row fleet-row" data-name="${escapeHtml(c.name)}" data-state="${escapeHtml(c.state)}">
      <div class="rule-main">
        <span class="fleet-row-name"><span class="dot ${stateClass}"></span>${escapeHtml(c.label)}${c.note ? `<span class="fleet-row-sub">${escapeHtml(c.note)}</span>` : ""}</span>
        <span class="fleet-row-image" title="${escapeHtml(c.image)}">${escapeHtml(c.image)}</span>
      </div>
      <span class="fleet-row-health">${escapeHtml(healthLabel)}</span>
      <span class="fleet-metric">CPU <span class="fleet-bar"><span class="fleet-bar-fill ${cpuCls}" style="width:${cpuPct}%"></span></span> ${fmtPercent(c.cpu_percent)}</span>
      <span class="fleet-metric">MEM <span class="fleet-bar"><span class="fleet-bar-fill ${memCls}" style="width:${memPct}%"></span></span> ${fmtMb(c.mem_used_mb)}</span>
      <div class="rule-actions">
        <button class="btn-icon" type="button" data-act="tail" title="Tail logs" aria-label="Tail logs for ${escapeHtml(c.label)}">${svg("tail")}</button>
        <button class="btn-icon" type="button" data-act="start" title="Start" aria-label="Start ${escapeHtml(c.label)}" ${c.state === "running" ? "disabled" : ""}>${svg("start")}</button>
        <button class="btn-icon" type="button" data-act="stop" title="Stop" aria-label="Stop ${escapeHtml(c.label)}" ${c.is_self || c.state !== "running" ? "disabled" : ""}>${svg("stop")}</button>
        <button class="btn-icon" type="button" data-act="restart" title="Restart" aria-label="Restart ${escapeHtml(c.label)}" ${c.is_self ? "disabled" : ""}>${svg("restart")}</button>
      </div>
    </div>`;
}

function wireFleetRow(row, c) {
  const tailBtn = row.querySelector('[data-act="tail"]');
  const startBtn = row.querySelector('[data-act="start"]');
  const stopBtn = row.querySelector('[data-act="stop"]');
  const restartBtn = row.querySelector('[data-act="restart"]');

  tailBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    selectLogSource(c.name);
    document.querySelectorAll(".fleet-row.selected").forEach((r) => r.classList.remove("selected"));
    row.classList.add("selected");
  });

  const fire = async (btn, action, label) => {
    btn.disabled = true;
    btn.classList.add("spinning");
    logLine("pending", `${c.label} — ${label} requested`);
    try {
      const data = await postAction(`/api/container/${c.name}/${action}`);
      logLine("ok", `${c.label} — ${data.message}`);
    } catch (e) {
      logLine("err", `${c.label} — ${e.message}`);
    } finally {
      btn.classList.remove("spinning");
      refreshFleet();
    }
  };
  if (!startBtn.disabled) startBtn.addEventListener("click", (e) => { e.stopPropagation(); fire(startBtn, "start", "start"); });
  if (!restartBtn.disabled) restartBtn.addEventListener("click", (e) => { e.stopPropagation(); fire(restartBtn, "restart", "restart"); });
  if (!stopBtn.disabled) armIconButton(stopBtn, "stop", () => fire(stopBtn, "stop", "stop"), (e) => e.stopPropagation());
}

let fleetBuilt = false;
let previousHitCounts = {};

async function fetchHitCounts() {
  try {
    const res = await fetch("/api/api-hit-counts");
    if (!res.ok) return null;
    const { counts } = await res.json();
    previousHitCounts = counts;
    return counts;
  } catch (e) {
    return null;
  }
}

function populateLogSourceSelect(data) {
  const select = document.getElementById("log-source");
  const prevValue = select.value;
  const byGroup = {};
  for (const c of data) {
    const group = FLEET_GROUPS[c.name] || "Other";
    (byGroup[group] = byGroup[group] || []).push(c);
  }
  let html = '<option value="">Select a source…</option>';
  for (const group of GROUP_ORDER) {
    if (!byGroup[group]) continue;
    html += `<optgroup label="${escapeHtml(group)}">`;
    for (const c of byGroup[group].sort((a, b) => a.label.localeCompare(b.label))) {
      html += `<option value="${escapeHtml(c.name)}">${escapeHtml(c.label)}</option>`;
    }
    html += `</optgroup>`;
  }
  select.innerHTML = html;
  select.value = prevValue;
}

export async function refreshFleet() {
  const wrap = document.getElementById("fleet-groups");
  let data;
  try {
    const res = await fetch("/api/containers");
    data = await res.json();
    if (!res.ok) throw new Error("Could not load containers");
  } catch (e) {
    if (!fleetBuilt) wrap.innerHTML = `<div class="hint error">Could not load containers.</div>`;
    return;
  }

  const up = data.filter((c) => c.state === "running" && (c.health === "healthy" || !c.health)).length;
  const containersValue = document.getElementById("stat-containers-value");
  const containersSub = document.getElementById("stat-containers-sub");
  if (containersValue) containersValue.textContent = `${up} / ${data.length}`;
  if (containersSub) containersSub.textContent = up === data.length ? "all healthy" : `${data.length - up} need attention`;

  const hits = await fetchHitCounts();
  for (const c of data) {
    const hist = groupHistoryFor(c.name);
    pushHistory(hist.cpu, c.cpu_percent ?? 0, FLEET_HISTORY_LEN);
    pushHistory(hist.mem, c.mem_percent ?? 0, FLEET_HISTORY_LEN);
  }
  const byGroup = {};
  for (const c of data) {
    const group = FLEET_GROUPS[c.name] || "Other";
    (byGroup[group] = byGroup[group] || []).push(c);
  }

  wrap.innerHTML = "";
  for (const group of GROUP_ORDER) {
    const items = byGroup[group];
    if (!items) continue;
    items.sort((a, b) => a.label.localeCompare(b.label));
    const groupEl = document.createElement("div");
    groupEl.className = "fleet-group" + (collapsedGroups.has(group) ? " collapsed" : "");
    const downCount = items.filter((c) => !(c.state === "running" && (c.health === "healthy" || !c.health))).length;
    // Per-group summary sparkline: max CPU% across the group's containers
    // per poll, not one sparkline per container (unreadable at this density).
    const groupCpuHistory = groupHistoryFor(`__group__${group}`);
    pushHistory(groupCpuHistory.cpu, Math.max(0, ...items.map((c) => c.cpu_percent ?? 0)), FLEET_HISTORY_LEN);
    groupEl.innerHTML = `
      <div class="fleet-group-head" data-group="${escapeHtml(group)}">
        <span class="chev">▾</span>${escapeHtml(group)}
        <span class="fleet-group-count">${items.length} container${items.length === 1 ? "" : "s"}${downCount ? ` · ${downCount} need attention` : ""}</span>
        <svg class="sparkline fleet-group-spark" viewBox="0 0 200 40" preserveAspectRatio="none"></svg>
      </div>
      <div class="rule-list">${items.map(fleetRowHtml).join("")}</div>
    `;
    wrap.appendChild(groupEl);
    renderSparkline(groupEl.querySelector(".fleet-group-spark"), groupCpuHistory.cpu, { min: 0, max: 100 });
    groupEl.querySelector(".fleet-group-head").addEventListener("click", () => {
      groupEl.classList.toggle("collapsed");
      if (groupEl.classList.contains("collapsed")) collapsedGroups.add(group);
      else collapsedGroups.delete(group);
      localStorage.setItem("fleetCollapsed", JSON.stringify([...collapsedGroups]));
    });
    groupEl.querySelectorAll(".fleet-row").forEach((row) => {
      const c = items.find((x) => x.name === row.dataset.name);
      if (c.name === getActiveLogName()) row.classList.add("selected");
      wireFleetRow(row, c);
    });
  }
  fleetBuilt = true;
  populateLogSourceSelect(data);
  renderStatusDots(data);
}
