/* Activity strip (compact recent-action log, pinned under the log
   console) and the pinned log console itself (right column) - the one
   place any container's logs stream to, whether picked manually from
   the source select or opened automatically because a palette command
   targets a container. */
import { escapeHtml, formatLogLine } from "./core.js";
import { openConsole } from "./settings.js";

const MAX_ACTIVITY_LINES = 80;

export function logLine(kind, text) {
  const body = document.getElementById("log-body");
  const t = new Date().toLocaleTimeString([], { hour12: false });
  const glyph = kind === "ok" ? "✓" : kind === "err" ? "✕" : "›";
  const el = document.createElement("div");
  el.className = `activity-line ${kind}`;
  el.innerHTML = `<span class="t">${t}</span> <span class="g">${glyph}</span> ${escapeHtml(text)}`;
  body.appendChild(el);
  while (body.children.length > MAX_ACTIVITY_LINES) body.removeChild(body.firstChild);
  body.scrollTop = body.scrollHeight;
}

let activeLogSource = null;
let activeLogName = null;

export function getActiveLogName() {
  return activeLogName;
}

export function selectLogSource(name) {
  const lines = document.getElementById("log-lines");
  const select = document.getElementById("log-source");
  if (activeLogSource) {
    activeLogSource.close();
    activeLogSource = null;
  }
  activeLogName = name || null;
  if (select && select.value !== (name || "")) select.value = name || "";
  if (!name) {
    lines.innerHTML = '<span class="log-empty">Select a container above, or run a command from the palette — its log will stream here.</span>';
    return;
  }
  lines.textContent = "";
  openConsole();
  activeLogSource = new EventSource(`/api/container/${encodeURIComponent(name)}/logs/stream`);
  activeLogSource.onmessage = (ev) => {
    lines.textContent += formatLogLine(ev.data) + "\n";
    lines.scrollTop = lines.scrollHeight;
  };
  activeLogSource.onerror = () => {
    lines.textContent += "\n[stream disconnected]\n";
  };
}

export function wireLogConsole() {
  document.getElementById("log-source").addEventListener("change", (e) => selectLogSource(e.target.value || null));
  document.getElementById("log-clear").addEventListener("click", () => {
    document.getElementById("log-lines").textContent = "";
  });
}
