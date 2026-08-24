/* Shared primitives used across every module: icons, HTML escaping, log
   line timestamp reformatting, the generic POST helper, and the
   status-line class toggler. No DOM structure of its own. */

export const ICONS = {
  bolt: '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/>',
  broom: '<path d="M9.59 4.59A2 2 0 1111 8H2"/><path d="M12.59 11.59A2 2 0 1114 15H2"/><path d="M17.73 7.73A2.5 2.5 0 1119.5 12H2"/>',
  stop: '<rect x="6" y="6" width="12" height="12"/>',
  start: '<polygon points="6 3 20 12 6 21 6 3"/>',
  restart: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>',
  tail: '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
};

export function svg(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}

export function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}

/* Docker's own timestamps=True prefixes each log line with its real
   RFC3339Nano write time (server-side, not this browser's receipt
   time) - reformat it to a compact local clock instead of stripping it.
   Lines with no such prefix (anything not sourced from a docker.logs()
   call) pass through unchanged. */
const LOG_TS_RE = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s(.*)$/;

export function formatLogLine(line) {
  const m = LOG_TS_RE.exec(line);
  if (!m) return line;
  const t = new Date(m[1]).toLocaleTimeString([], { hour12: false });
  return `[${t}] ${m[2]}`;
}

export function formatLogText(raw) {
  return raw.split("\n").map(formatLogLine).join("\n");
}

export async function postAction(url, body) {
  const opts = { method: "POST" };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  let data = null;
  try {
    data = await res.json();
  } catch (_) { /* no body */ }
  if (!res.ok) {
    const msg = data?.detail?.message || data?.message || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

export function setStatusLine(el, state, text) {
  el.textContent = text;
  el.className = el.className.replace(/state-\S+/g, "").trim();
  el.classList.add(`state-${state}`);
}
