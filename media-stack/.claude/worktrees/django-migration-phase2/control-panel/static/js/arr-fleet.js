/* Arr fleet detail — Radarr/Sonarr actions, unchanged behavior, just
   restyled without the card class. */
import { escapeHtml, postAction, setStatusLine } from "./core.js";
import { logLine } from "./activity-log.js";
import { fetchAndRender } from "./result-render.js";
import { armButton } from "./buttons.js";

/* id is the core/arr_client.py ARR_APPS key (underscore), which is what
   every /api/arr/{app_name}/... route matches on - NOT the Docker
   container name (hyphen). port is the published host port. */
const ARR_APPS = [
  { id: "radarr", label: "Radarr", port: 7878 },
  { id: "sonarr", label: "Sonarr", port: 8989 },
];
const ARR_FLEET_ACTIONS = [
  { id: "queue-status", label: "Queue status", path: "/api/queue-status" },
  { id: "queue-errors", label: "Queue errors", path: "/api/arr/queue-errors" },
  { id: "command-queue-summary", label: "Command queue summary", path: "/api/arr/command-queue-summary" },
  { id: "backlog-status", label: "Backlog ETA", path: "/api/backlog-status" },
  { id: "prowlarr-indexers", label: "Prowlarr indexers", path: "/api/prowlarr/indexers" },
];
const ARR_VIEWS = [
  { id: "backlog", label: "Backlog", path: (id) => `/api/arr/${id}/command-backlog` },
  { id: "missing-aired", label: "Missing aired", path: (id) => `/api/arr/${id}/missing-aired` },
  { id: "cutoff-unmet", label: "Cutoff unmet", path: (id) => `/api/arr/${id}/cutoff-unmet?limit=25` },
  { id: "recently-added", label: "Recently added", path: (id) => `/api/arr/${id}/recently-added?limit=15` },
  { id: "import-lists", label: "Import lists", path: (id) => `/api/arr/${id}/import-lists` },
  { id: "logs", label: "Logs", path: (id) => `/api/arr/${id}/logs?lines=150` },
];

export function buildArrFleet() {
  const wrap = document.getElementById("arr-fleet");
  if (!wrap) return;

  const toolbarRow = document.createElement("div");
  toolbarRow.className = "arr-actions-row";
  toolbarRow.innerHTML = `<span class="arr-actions-row-label">Fleet-wide</span>` + ARR_FLEET_ACTIONS.map((a) => `<button class="btn-ghost" data-fleet="${a.id}" type="button">${a.label}</button>`).join("");
  const toolbarPanel = document.createElement("div");
  toolbarPanel.className = "arr-panel";
  toolbarPanel.hidden = true;
  wrap.appendChild(toolbarRow);
  wrap.appendChild(toolbarPanel);
  toolbarRow.querySelectorAll("[data-fleet]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const wasOpen = btn.classList.contains("active") && !toolbarPanel.hidden;
      toolbarRow.querySelectorAll("[data-fleet]").forEach((b) => b.classList.remove("active"));
      if (wasOpen) { toolbarPanel.hidden = true; return; }
      btn.classList.add("active");
      const action = ARR_FLEET_ACTIONS.find((a) => a.id === btn.dataset.fleet);
      logLine("pending", `${action.label} — requested`);
      try {
        await fetchAndRender(toolbarPanel, "GET", action.path);
        logLine("ok", `${action.label} — loaded`);
      } catch (e) {
        logLine("err", `${action.label} — ${e.message}`);
      }
    });
  });

  for (const app of ARR_APPS) {
    const openUrl = `${location.protocol}//${location.hostname}:${app.port}`;
    const block = document.createElement("div");
    block.className = "arr-block";
    block.innerHTML = `
      <div class="arr-head">
        <div class="arr-name"><span class="dot unknown" id="arr-dot-${app.id}"></span>${app.label}</div>
        <a class="arr-link" href="${openUrl}" target="_blank" rel="noopener">open UI ↗</a>
        <label class="switch" data-search-toggle="${app.id}" title="RSS sync + automatic search, every indexer — click twice to confirm, this fans out to all of them">
          <input type="checkbox" disabled>
          <span class="switch-track"></span>
          <span class="switch-label">Auto search</span>
        </label>
        <div class="arr-status" id="arr-status-${app.id}">—</div>
      </div>
      <form class="arr-search" data-app="${app.id}">
        <input type="search" placeholder="Search ${app.label}…" aria-label="Search ${app.label}" required>
        <button class="btn-ghost" type="submit">Search</button>
      </form>
      <div class="arr-actions-row">
        <span class="arr-actions-row-label">Run</span>
        <button class="btn-primary" data-action="rss-sync" type="button">RSS sync</button>
        <button class="btn-primary" data-action="search-missing" type="button">Search missing</button>
        <button class="btn-ghost" data-unstick type="button">Unstick</button>
        <button class="btn-ghost" data-unstick-importing type="button">Unstick importing</button>
      </div>
      <div class="arr-actions-row">
        <span class="arr-actions-row-label">View</span>
        ${ARR_VIEWS.map((v) => `<button class="btn-ghost" data-view="${v.id}" type="button">${v.label}</button>`).join("")}
        <button class="btn-ghost" data-view="manual-import" type="button">Manual import</button>
      </div>
      <div class="arr-panel" id="arr-panel-${app.id}" hidden></div>
    `;
    wrap.appendChild(block);

    const status = block.querySelector(".arr-status");
    const panel = block.querySelector(`#arr-panel-${app.id}`);

    block.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        const label = action === "rss-sync" ? "RSS sync" : "Search missing";
        block.querySelectorAll("[data-action]").forEach((b) => (b.disabled = true));
        setStatusLine(status, "pending", `${label}…`);
        logLine("pending", `${app.label} ${label} — requested`);
        try {
          const data = await postAction(`/api/arr/${app.id}/${action}`);
          setStatusLine(status, "success", data.message);
          logLine("ok", `${app.label} ${label} — ${data.message}`);
        } catch (e) {
          setStatusLine(status, "error", e.message);
          logLine("err", `${app.label} ${label} — ${e.message}`);
        } finally {
          block.querySelectorAll("[data-action]").forEach((b) => (b.disabled = false));
        }
      });
    });

    setupUnstick(app, block, status);
    setupUnstickImporting(app, block, status);
    setupSearchToggle(app, block, status);

    const searchForm = block.querySelector(".arr-search");
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = searchForm.querySelector("input");
      const term = input.value.trim();
      if (!term) return;
      window.open(`${openUrl}/add/new?term=${encodeURIComponent(term)}`, "_blank", "noopener");
      logLine("ok", `${app.label} search — opened "${term}" in a new tab`);
      input.value = "";
    });

    block.querySelectorAll("[data-view]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const wasOpen = btn.classList.contains("active") && !panel.hidden;
        block.querySelectorAll("[data-view]").forEach((b) => b.classList.remove("active"));
        if (wasOpen) { panel.hidden = true; return; }
        btn.classList.add("active");
        if (btn.dataset.view === "manual-import") {
          await loadManualImportCandidates(app, panel);
          return;
        }
        const view = ARR_VIEWS.find((v) => v.id === btn.dataset.view);
        logLine("pending", `${app.label} ${view.label} — requested`);
        try {
          await fetchAndRender(panel, "GET", view.path(app.id));
          logLine("ok", `${app.label} ${view.label} — loaded`);
        } catch (e) {
          logLine("err", `${app.label} ${view.label} — ${e.message}`);
        }
      });
    });
  }
}

function setupUnstick(app, block, status) {
  const btn = block.querySelector("[data-unstick]");
  if (!btn) return;
  armButton(btn, "Unstick", "Confirm — removes + blocklists", async () => {
    btn.disabled = true;
    setStatusLine(status, "pending", "Unsticking…");
    logLine("pending", `${app.label} unstick — requested`);
    try {
      const data = await postAction(`/api/arr/${app.id}/unstick`);
      setStatusLine(status, "success", data.message);
      logLine("ok", `${app.label} unstick — ${data.message}`);
    } catch (e) {
      setStatusLine(status, "error", e.message);
      logLine("err", `${app.label} unstick — ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  });
}

async function setupSearchToggle(app, block, status) {
  const label = block.querySelector("[data-search-toggle]");
  if (!label) return;
  const input = label.querySelector("input");
  const track = label.querySelector(".switch-track");

  try {
    const res = await fetch(`/api/arr/${app.id}/search-status`);
    const data = await res.json();
    if (res.ok) input.checked = data.enabled;
  } catch (_) { /* leave unchecked, still disabled below until confirmed reachable */ }
  input.disabled = false;

  // Real read+write state, but the write fans out a PUT to every
  // indexer - same arm/confirm-within-5s pattern as the other
  // destructive controls here, just applied to a switch instead of a
  // button. The checkbox itself never flips on a bare click; only a
  // confirmed toggle changes it, so it always reflects real state.
  let armed = false;
  let disarmTimer = null;
  const disarm = () => { armed = false; track.classList.remove("armed"); };
  label.addEventListener("click", (e) => {
    e.preventDefault();
    if (input.disabled) return;
    if (!armed) {
      armed = true;
      track.classList.add("armed");
      disarmTimer = setTimeout(disarm, 5000);
      return;
    }
    clearTimeout(disarmTimer);
    disarm();
    const next = !input.checked;
    (async () => {
      input.disabled = true;
      setStatusLine(status, "pending", `${next ? "Enabling" : "Disabling"} auto search…`);
      logLine("pending", `${app.label} auto search — ${next ? "enable" : "disable"} requested`);
      try {
        const data = await postAction(`/api/arr/${app.id}/search-toggle?enabled=${next}`);
        input.checked = next;
        setStatusLine(status, "success", data.message);
        logLine("ok", `${app.label} auto search — ${data.message}`);
      } catch (err) {
        setStatusLine(status, "error", err.message);
        logLine("err", `${app.label} auto search — ${err.message}`);
      } finally {
        input.disabled = false;
      }
    })();
  });
}

function setupUnstickImporting(app, block, status) {
  const btn = block.querySelector("[data-unstick-importing]");
  if (!btn) return;
  armButton(btn, "Unstick importing", "Confirm — verifies + clears", async () => {
    btn.disabled = true;
    setStatusLine(status, "pending", "Checking importing downloads…");
    logLine("pending", `${app.label} unstick importing — requested`);
    try {
      const data = await postAction(`/api/arr/${app.id}/unstick-importing`);
      setStatusLine(status, "success", data.message);
      logLine("ok", `${app.label} unstick importing — ${data.message}`);
    } catch (e) {
      setStatusLine(status, "error", e.message);
      logLine("err", `${app.label} unstick importing — ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  });
}

async function loadManualImportCandidates(app, panel) {
  panel.hidden = false;
  panel.innerHTML = `<div class="hint">Scanning stuck downloads for importable files…</div>`;
  logLine("pending", `${app.label} manual import — scanning`);
  try {
    const res = await fetch(`/api/arr/${app.id}/manual-import`);
    const items = await res.json();
    if (!res.ok) throw new Error(items?.detail?.message || items?.message || `Scan failed (${res.status})`);
    renderManualImportCandidates(app, panel, items);
    logLine("ok", `${app.label} manual import — found ${items.length} importable file${items.length === 1 ? "" : "s"}`);
  } catch (e) {
    panel.innerHTML = `<div class="hint error">${escapeHtml(e.message)}</div>`;
    logLine("err", `${app.label} manual import — ${e.message}`);
  }
}

function renderManualImportCandidates(app, panel, items) {
  if (!items.length) {
    panel.innerHTML = `<div class="hint">No importable files found among currently stuck downloads.</div>`;
    return;
  }
  panel.innerHTML = items
    .map((item, i) => {
      const meta = [item.quality, item.release_group, item.size].filter(Boolean).join(" · ");
      const match = [item.match_title, item.episode].filter(Boolean).join(" — ");
      const rejections = item.rejections.length
        ? `<span class="result-rejections" title="${escapeHtml(item.rejections.join("; "))}">⚠ ${item.rejections.length} rejection${item.rejections.length === 1 ? "" : "s"}</span>`
        : "";
      return `
        <div class="result-row-item">
          <div class="result-row-main">
            <span class="result-title">${escapeHtml(match || item.name || "Unknown")}</span>
            ${rejections}
            <span class="result-meta">${escapeHtml(meta)}</span>
          </div>
          <button class="btn-ghost import-run" type="button" data-idx="${i}">Import</button>
          <div class="rule-status" id="import-status-${app.id}-${i}">—</div>
        </div>`;
    })
    .join("");
  panel.querySelectorAll("button.import-run").forEach((btn) => {
    const item = items[Number(btn.dataset.idx)];
    const status = panel.querySelector(`#import-status-${app.id}-${btn.dataset.idx}`);
    armButton(btn, "Import", "Confirm import?", async () => {
      btn.disabled = true;
      setStatusLine(status, "pending", "Importing…");
      logLine("pending", `${app.label} manual import — "${item.name}" requested`);
      try {
        const data = await postAction(`/api/arr/${app.id}/manual-import`, item.file);
        setStatusLine(status, "success", data.message);
        logLine("ok", `${app.label} manual import — ${data.message}`);
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `${app.label} manual import — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });
}
