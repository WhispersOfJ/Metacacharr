/* Letterboxd tracked-list management + sync history — mirrors
   loop-remediation.js's toolbar-row/on-demand-panel pattern: nothing here
   polls, every view is a manual "Show" click, same as every other
   fleet-rail subsystem.

   Styled as its own instrument rather than a plain table: Letterboxd's
   real tri-dot logomark as the section's identifying mark (same role the
   conic-gradient brand-mark plays in the topbar), tracked rows drawn as
   film frames with a sprocket edge, and sync runs as a filmstrip of
   colour-coded delta chips instead of an alphabetised generic table. */
import { escapeHtml, postAction } from "./core.js";
import { logLine } from "./activity-log.js";

const LB_MARK = `
  <span class="lb-mark" aria-hidden="true">
    <span class="lb-dot lb-dot-a"></span>
    <span class="lb-dot lb-dot-b"></span>
    <span class="lb-dot lb-dot-c"></span>
  </span>`;

export function buildLetterboxdPanel() {
  const wrap = document.getElementById("letterboxd-panel");
  if (!wrap) return;

  const form = document.createElement("form");
  form.className = "arr-actions-row lb-track-form";
  form.innerHTML = `
    <span class="arr-actions-row-label">${LB_MARK}Track a list</span>
    <input type="url" placeholder="https://letterboxd.com/<user>/watchlist/" required data-track-url style="flex: 1; min-width: 240px;">
    <input type="text" placeholder="Label (optional)" data-track-label style="max-width: 200px;">
    <button class="btn-primary lb-track-btn" type="submit">Track</button>
  `;
  wrap.appendChild(form);

  const toolbarRow = document.createElement("div");
  toolbarRow.className = "arr-actions-row";
  toolbarRow.innerHTML = `
    <span class="arr-actions-row-label">Reels</span>
    <button class="btn-ghost" data-lb="tracked" type="button">Tracked lists</button>
    <button class="btn-ghost" data-lb="history" type="button">Sync history</button>
  `;
  const panel = document.createElement("div");
  panel.className = "arr-panel";
  panel.hidden = true;
  wrap.appendChild(toolbarRow);
  wrap.appendChild(panel);

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const url = form.querySelector("[data-track-url]").value.trim();
    const label = form.querySelector("[data-track-label]").value.trim();
    logLine("pending", `Letterboxd track — ${url}`);
    try {
      await postAction("/api/arr/letterboxd/track", label ? { url, label } : { url });
      logLine("ok", `Letterboxd track — now tracking ${url}`);
      form.reset();
      if (!panel.hidden && panel.dataset.lbView === "tracked") await showTracked(panel);
    } catch (e) {
      logLine("err", `Letterboxd track — ${e.message}`);
    }
  });

  toolbarRow.querySelectorAll("[data-lb]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const wasOpen = btn.classList.contains("active") && !panel.hidden;
      toolbarRow.querySelectorAll("[data-lb]").forEach((b) => b.classList.remove("active"));
      if (wasOpen) { panel.hidden = true; return; }
      btn.classList.add("active");
      const view = btn.dataset.lb;
      logLine("pending", `Letterboxd ${view} — requested`);
      try {
        if (view === "tracked") {
          panel.dataset.lbView = "tracked";
          await showTracked(panel);
        } else {
          panel.dataset.lbView = "history";
          await showHistory(panel);
        }
        logLine("ok", `Letterboxd ${view} — loaded`);
      } catch (e) {
        logLine("err", `Letterboxd ${view} — ${e.message}`);
      }
    });
  });
}

/* Relative-time label, matched to the nightly sync cadence rather than a
   generic "Nd ago" — "synced last night" reads truer for a once-a-day job
   than a raw hour count would. */
function timeAgo(iso) {
  if (!iso) return { text: "never", freshness: "cold" };
  const ms = Date.now() - new Date(iso).getTime();
  const hours = ms / 3_600_000;
  if (hours < 26) return { text: hours < 1 ? "just now" : `${Math.round(hours)}h ago`, freshness: "fresh" };
  const days = Math.round(hours / 24);
  if (days < 8) return { text: `${days}d ago`, freshness: "stale" };
  return { text: `${days}d ago`, freshness: "cold" };
}

async function fetchJson(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail?.message || data?.message || `Request failed (${res.status})`);
  return data;
}

async function showTracked(panel) {
  panel.hidden = false;
  panel.innerHTML = `<div class="hint">Loading…</div>`;
  const data = await fetchJson("/api/arr/letterboxd/tracked");
  renderTracked(panel, data.lists || []);
}

function renderTracked(panel, lists) {
  if (!lists.length) {
    panel.innerHTML = `<div class="hint">No tracked lists yet — track one above and it joins the nightly reel.</div>`;
    return;
  }
  const rows = lists.map((l) => {
    const { text, freshness } = timeAgo(l.lastSyncedAt);
    return `
    <div class="lb-frame" data-lb-frame>
      <div class="lb-frame-sprocket" aria-hidden="true"></div>
      <div class="lb-frame-body">
        <div class="lb-frame-title">${escapeHtml(l.label || l.url)}</div>
        <a class="lb-frame-url" href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${escapeHtml(l.url)}</a>
      </div>
      <span class="lb-pill lb-pill-${freshness}">${escapeHtml(text)}</span>
      <button class="btn-ghost lb-untrack" data-untrack-url="${escapeHtml(l.url)}" type="button">Untrack</button>
    </div>`;
  }).join("");
  panel.innerHTML = `<div class="lb-filmstrip">${rows}</div>`;
  panel.querySelectorAll("[data-untrack-url]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.dataset.untrackUrl;
      logLine("pending", `Letterboxd untrack — ${url}`);
      try {
        await postAction("/api/arr/letterboxd/untrack", { url });
        logLine("ok", `Letterboxd untrack — stopped tracking ${url}`);
        await showTracked(panel);
      } catch (e) {
        logLine("err", `Letterboxd untrack — ${e.message}`);
      }
    });
  });
}

async function showHistory(panel) {
  panel.hidden = false;
  panel.innerHTML = `<div class="hint">Loading…</div>`;
  const [historyData, trackedData] = await Promise.all([
    fetchJson("/api/arr/letterboxd/history"),
    fetchJson("/api/arr/letterboxd/tracked").catch(() => ({ lists: [] })),
  ]);
  const labelByUrl = new Map((trackedData.lists || []).map((l) => [l.url, l.label || l.url]));
  renderHistory(panel, historyData.runs || [], labelByUrl);
}

function chip(cls, symbol, value, title) {
  if (!value) return "";
  return `<span class="lb-chip lb-chip-${cls}" title="${escapeHtml(title)}">${symbol}${value}</span>`;
}

function renderHistory(panel, runs, labelByUrl) {
  if (!runs.length) {
    panel.innerHTML = `<div class="hint">No sync runs recorded yet.</div>`;
    return;
  }
  const rows = runs.map((r) => {
    const { text } = timeAgo(r.runAt);
    const label = labelByUrl.get(r.listUrl) || r.listUrl;
    const healthy = !r.failed && !r.errorDetail;
    const chips = [
      chip("added", "+", r.added, `${r.added} added to Radarr`),
      chip("crossover", "TV", r.tvCrossover, `${r.tvCrossover} routed to Sonarr as a TV crossover`),
      chip("already", "=", r.already, `${r.already} already in the library`),
      chip("unmatched", "?", r.unmatched, `${r.unmatched} unmatched`),
      chip("failed", "!", r.failed, `${r.failed} failed`),
    ].join("");
    return `
    <div class="lb-run ${healthy ? "lb-run-ok" : "lb-run-bad"}">
      <span class="lb-run-dot" aria-hidden="true"></span>
      <div class="lb-run-main">
        <div class="lb-run-title">${escapeHtml(label)}</div>
        <div class="lb-run-time">${escapeHtml(text)} · matched ${r.matched ?? 0}</div>
        ${r.errorDetail ? `<div class="lb-run-error">${escapeHtml(r.errorDetail)}</div>` : ""}
      </div>
      <div class="lb-run-chips">${chips || `<span class="lb-chip lb-chip-already">=0</span>`}</div>
    </div>`;
  }).join("");
  panel.innerHTML = `<div class="lb-filmstrip">${rows}</div>`;
}
