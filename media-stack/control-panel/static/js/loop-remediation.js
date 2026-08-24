/* Loop remediation toolkit — manual UI for the unmonitor/exclude decision
   tree used by hand throughout the 2026-08-01/02 queue-autofix sessions.
   Not a poller: on-demand "Rescan" only, same as Manual Import. */
import { escapeHtml, postAction } from "./core.js";
import { logLine } from "./activity-log.js";
import { armButton } from "./buttons.js";

const APPS = [
  { id: "radarr", label: "Radarr" },
  { id: "sonarr", label: "Sonarr" },
];

const ACTION_COPY = {
  unmonitor: { label: "Unmonitor", confirm: "Confirm — unmonitor" },
  "review-profile": null,
  "suffix-bug": null,
  none: null,
};

export function buildLoopRemediation() {
  const wrap = document.getElementById("loop-remediation");
  if (!wrap) return;

  const faders = document.createElement("div");
  faders.className = "arr-actions-row";
  faders.innerHTML = `
    <div class="fader" data-fader="failed_pending_storm_threshold">
      <span class="arr-actions-row-label">Failed-pending storm threshold</span>
      <div class="fader-row">
        <input type="range" class="fader-input" min="3" max="50" step="1" disabled>
        <span class="fader-value">—</span>
      </div>
    </div>
    <div class="fader" data-fader="loop_review_profile_threshold">
      <span class="arr-actions-row-label">Loop review-profile threshold</span>
      <div class="fader-row">
        <input type="range" class="fader-input" min="2" max="30" step="1" disabled>
        <span class="fader-value">—</span>
      </div>
    </div>
  `;
  wrap.appendChild(faders);
  wireFader(faders, "failed_pending_storm_threshold");
  wireFader(faders, "loop_review_profile_threshold");

  const row = document.createElement("div");
  row.className = "arr-actions-row";
  row.innerHTML = `<span class="arr-actions-row-label">Loop remediation</span><button class="btn-ghost" data-rescan type="button">Rescan</button><button class="btn-ghost" data-nzbdav-check type="button">Check NzbDAV dedup config</button>`;
  const panel = document.createElement("div");
  panel.className = "arr-panel";
  wrap.appendChild(row);
  wrap.appendChild(panel);

  row.querySelector("[data-rescan]").addEventListener("click", () => rescan(panel));
  row.querySelector("[data-nzbdav-check]").addEventListener("click", () => checkNzbdavConfig());
}

async function wireFader(faders, key) {
  const wrap = faders.querySelector(`[data-fader="${key}"]`);
  const input = wrap.querySelector(".fader-input");
  const value = wrap.querySelector(".fader-value");

  try {
    const res = await fetch("/api/settings");
    const settings = await res.json();
    input.value = settings[key];
    value.textContent = settings[key];
    input.disabled = false;
  } catch (_) { /* leave disabled - settings unreachable */ }

  input.addEventListener("input", () => { value.textContent = input.value; });
  input.addEventListener("change", async () => {
    input.disabled = true;
    try {
      await fetch("/api/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: Number(input.value) }),
      });
      logLine("ok", `${key.replace(/_/g, " ")} — set to ${input.value}`);
    } catch (e) {
      logLine("err", `${key.replace(/_/g, " ")} — ${e.message}`);
    } finally {
      input.disabled = false;
    }
  });
}

async function checkNzbdavConfig() {
  logLine("pending", "NzbDAV dedup config check — requested");
  try {
    const res = await fetch("/api/nzbdav/dedup-config-check");
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail?.message || data?.message || `Check failed (${res.status})`);
    logLine(data.healthy ? "ok" : "err", `NzbDAV dedup config — ${data.message}`);
  } catch (e) {
    logLine("err", `NzbDAV dedup config — ${e.message}`);
  }
}

async function rescan(panel) {
  panel.hidden = false;
  panel.innerHTML = `<div class="hint">Scanning Radarr/Sonarr history for looping titles…</div>`;
  logLine("pending", "Loop remediation — rescanning");
  try {
    const results = await Promise.all(APPS.map((a) => fetchCandidates(a.id)));
    const rows = results.flatMap((r, i) => r.candidates.map((c) => ({ ...c, app: APPS[i].id, appLabel: APPS[i].label })));
    renderRows(panel, rows);
    logLine("ok", `Loop remediation — ${rows.length} looping candidate(s) found`);
  } catch (e) {
    panel.innerHTML = `<div class="hint error">${escapeHtml(e.message)}</div>`;
    logLine("err", `Loop remediation — ${e.message}`);
  }
}

async function fetchCandidates(appId) {
  const res = await fetch(`/api/arr/${appId}/loop-candidates`);
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail?.message || data?.message || `Scan failed (${res.status})`);
  return data;
}

function renderRows(panel, rows) {
  if (!rows.length) {
    panel.innerHTML = `<div class="hint">No titles looping in the last 6h.</div>`;
    return;
  }
  panel.innerHTML = rows
    .map((r, i) => {
      const releases = r.releases.length ? `<span class="result-meta" title="${escapeHtml(r.releases.join("; "))}">${r.releases.length} release name(s)</span>` : "";
      const copy = ACTION_COPY[r.suggested_action];
      const actionHtml = copy
        ? `<button class="btn-ghost loop-action" type="button" data-idx="${i}">${copy.label}</button>`
        : `<span class="result-meta">${r.suggested_action === "review-profile" ? "Review quality profile" : r.suggested_action === "suffix-bug" ? "Dedup-suffix signature" : "No action"}</span>`;
      const excludeBtn = r.app === "radarr" ? `<button class="btn-ghost loop-exclude" type="button" data-idx="${i}">Exclude</button>` : "";
      return `
        <div class="result-row-item">
          <div class="result-row-main">
            <span class="result-title">${escapeHtml(r.appLabel)} — ${escapeHtml(r.title)}</span>
            <span class="result-meta">${r.occurrences}x failed</span>
            ${releases}
            <span class="result-meta" title="${escapeHtml(r.reason)}">${escapeHtml(r.reason)}</span>
          </div>
          ${actionHtml}
          ${excludeBtn}
          <div class="rule-status" id="loop-status-${i}">—</div>
        </div>`;
    })
    .join("");

  panel.querySelectorAll("button.loop-action").forEach((btn) => {
    const r = rows[Number(btn.dataset.idx)];
    const status = panel.querySelector(`#loop-status-${btn.dataset.idx}`);
    const copy = ACTION_COPY[r.suggested_action];
    armButton(btn, copy.label, copy.confirm, async () => {
      btn.disabled = true;
      logLine("pending", `${r.appLabel} unmonitor — "${r.title}" requested`);
      try {
        const data = await postAction(`/api/arr/${r.app}/unmonitor`, { ids: [r.id] });
        status.textContent = data.message;
        logLine("ok", `${r.appLabel} unmonitor — ${data.message}`);
      } catch (e) {
        status.textContent = e.message;
        logLine("err", `${r.appLabel} unmonitor — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });

  panel.querySelectorAll("button.loop-exclude").forEach((btn) => {
    const r = rows[Number(btn.dataset.idx)];
    const status = panel.querySelector(`#loop-status-${btn.dataset.idx}`);
    armButton(btn, "Exclude", "Confirm — permanent exclusion", async () => {
      btn.disabled = true;
      logLine("pending", `Radarr exclude — "${r.title}" requested`);
      try {
        const data = await postAction("/api/arr/radarr/exclude", { movieId: r.id });
        status.textContent = data.message;
        logLine("ok", `Radarr exclude — ${data.message}`);
      } catch (e) {
        status.textContent = e.message;
        logLine("err", `Radarr exclude — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });
}
