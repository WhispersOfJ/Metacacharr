/* Generic inline result rendering - turns whatever shape a GET/POST
   returns into real tables/definition-lists instead of a JSON dump. */
import { escapeHtml, formatLogText } from "./core.js";

const TABLE_COLUMN_PRIORITY = ["title", "name", "series", "episode", "label", "status", "message"];

function renderKv(el, obj) {
  const dl = document.createElement("dl");
  dl.className = "kv-grid";
  for (const key of Object.keys(obj)) {
    const v = obj[key];
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = v && typeof v === "object" ? JSON.stringify(v) : String(v);
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  el.appendChild(dl);
}

function renderTable(el, rows) {
  if (!rows.length) {
    el.innerHTML += `<div class="hint">No results.</div>`;
    return;
  }
  if (typeof rows[0] !== "object" || rows[0] === null) {
    const ul = document.createElement("ul");
    ul.className = "result-list";
    for (const v of rows) {
      const li = document.createElement("li");
      li.textContent = String(v);
      ul.appendChild(li);
    }
    el.appendChild(ul);
    return;
  }
  const keySet = new Set();
  for (const row of rows) for (const k of Object.keys(row || {})) keySet.add(k);
  const keys = [
    ...TABLE_COLUMN_PRIORITY.filter((k) => keySet.has(k)),
    ...[...keySet].filter((k) => !TABLE_COLUMN_PRIORITY.includes(k)).sort(),
  ];
  const wrap = document.createElement("div");
  wrap.className = "result-table-wrap";
  const table = document.createElement("table");
  table.className = "result-table";
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>${keys.map((k) => `<th>${escapeHtml(k)}</th>`).join("")}</tr>`;
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = keys
      .map((k) => {
        const v = (row || {})[k];
        const text = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
        return `<td class="${typeof v === "number" ? "num" : ""}">${escapeHtml(text)}</td>`;
      })
      .join("");
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  el.appendChild(wrap);
}

function resultSubhead(el, key) {
  const h = document.createElement("div");
  h.className = "result-subhead";
  h.textContent = key;
  el.appendChild(h);
}

function renderValue(el, key, value, depth) {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) {
    if (!value.length) return false;
    resultSubhead(el, key);
    renderTable(el, value);
    return true;
  }
  if (typeof value === "object") {
    if (!Object.keys(value).length) return false;
    resultSubhead(el, key);
    if (depth >= 2) {
      renderKv(el, value);
      return true;
    }
    let any = false;
    for (const k of Object.keys(value).sort()) {
      any = renderValue(el, k, value[k], depth + 1) || any;
    }
    if (!any) el.innerHTML += `<div class="hint">Empty.</div>`;
    return true;
  }
  if (typeof value === "string" && value.includes("\n")) {
    resultSubhead(el, key);
    const pre = document.createElement("pre");
    pre.className = "log-block";
    pre.textContent = formatLogText(value);
    el.appendChild(pre);
    return true;
  }
  renderKv(el, { [key]: value });
  return true;
}

export function renderResultPanel(el, data) {
  el.innerHTML = "";
  if (Array.isArray(data)) {
    renderTable(el, data);
    return;
  }
  data = data || {};
  let any = false;
  if (data.message) {
    const p = document.createElement("p");
    p.className = "result-summary";
    p.textContent = data.message;
    el.appendChild(p);
    any = true;
  }
  for (const key of Object.keys(data).sort()) {
    if (key === "message" || key === "ok" || key === "time") continue;
    any = renderValue(el, key, data[key], 0) || any;
  }
  if (!any) el.innerHTML = `<div class="hint">No data.</div>`;
}

export async function fetchAndRender(el, method, url, body) {
  el.hidden = false;
  el.innerHTML = `<div class="hint">Loading…</div>`;
  const opts = { method };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const raw = await res.text();
  let parsed = null;
  if (raw) {
    try { parsed = JSON.parse(raw); } catch (_) { parsed = null; }
  }
  if (!res.ok) {
    const msg = (parsed && (parsed.detail?.message || parsed.message)) || raw || `Request failed (${res.status})`;
    el.innerHTML = `<div class="hint error">${escapeHtml(msg)}</div>`;
    throw new Error(msg);
  }
  const payload = parsed && parsed.detail && typeof parsed.detail === "object" ? parsed.detail : parsed;
  renderResultPanel(el, payload);
  return payload;
}
