/* Command palette — Interaction model option C: the "doing" half of
   the split (viewing state is the panels above; triggering an action
   goes through here, reachable by fuzzy search regardless of where you
   are). Same list -> args -> confirm -> run flow as before, same
   manifest (static/commands.json); a running command's log now streams
   into the persistent right-column console instead of its own pane. */
import { escapeHtml } from "./core.js";
import { logLine, selectLogSource } from "./activity-log.js";

const consoleScreens = {
  list: document.getElementById("screen-list"),
  args: document.getElementById("screen-args"),
  confirm: document.getElementById("screen-confirm"),
  run: document.getElementById("screen-run"),
};

let commandRegistry = [];

function openPalette() {
  document.getElementById("palette-overlay").hidden = false;
  showConsoleScreen("list");
  const input = document.getElementById("console-filter");
  input.value = "";
  renderCommandList("");
  setTimeout(() => input.focus(), 30);
}

function closePalette() {
  document.getElementById("palette-overlay").hidden = true;
}

function showConsoleScreen(name) {
  for (const [key, el] of Object.entries(consoleScreens)) {
    if (el) el.hidden = key !== name;
  }
}

export function wirePalette() {
  document.getElementById("palette-open").addEventListener("click", openPalette);
  document.querySelectorAll("[data-close]").forEach((btn) => btn.addEventListener("click", closePalette));
  document.getElementById("palette-overlay").addEventListener("click", (e) => {
    if (e.target.id === "palette-overlay") closePalette();
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const overlay = document.getElementById("palette-overlay");
      overlay.hidden ? openPalette() : closePalette();
    } else if (e.key === "Escape" && !document.getElementById("palette-overlay").hidden) {
      closePalette();
    }
  });
  document.querySelectorAll("[data-back]").forEach((btn) => {
    btn.addEventListener("click", () => showConsoleScreen(btn.dataset.back));
  });
}

export async function loadCommandRegistry() {
  const statusLine = document.getElementById("console-status");
  try {
    const res = await fetch("/commands.json");
    commandRegistry = await res.json();
    statusLine.textContent = `${commandRegistry.length} operations loaded`;
    renderCommandList("");
  } catch (e) {
    statusLine.textContent = "Command manifest failed to load.";
  }
}

function fuzzyMatch(query, target) {
  if (!query) return true;
  let qi = 0;
  const q = query.toLowerCase();
  const t = target.toLowerCase();
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) qi++;
  }
  return qi === q.length;
}

function matchRank(query, cmd) {
  const q = query.toLowerCase();
  const name = cmd.Name.toLowerCase();
  if (name === q) return 0;
  if (name.startsWith(q)) return 1;
  if (name.includes(q)) return 2;
  if (fuzzyMatch(query, cmd.Name)) return 3;
  if (fuzzyMatch(query, cmd.Description)) return 4;
  return -1;
}

function renderCommandList(filterValue) {
  const list = document.getElementById("command-list");
  list.innerHTML = "";
  const matches = commandRegistry
    .map((c) => ({ c, rank: filterValue ? matchRank(filterValue, c) : 0 }))
    .filter((m) => m.rank !== -1)
    .sort((a, b) => a.rank - b.rank || a.c.Name.localeCompare(b.c.Name))
    .map((m) => m.c);
  for (const cmd of matches) {
    const li = document.createElement("li");
    const tag = cmd.Confirm ? '<span class="ctag">destructive</span>' : "";
    li.innerHTML = `<span class="cname">${escapeHtml(cmd.Name)}</span>${tag}<span class="cdesc">${escapeHtml(cmd.Description)}</span>`;
    li.addEventListener("click", () => openCommand(cmd));
    list.appendChild(li);
  }
}

const consoleFilterInput = document.getElementById("console-filter");
if (consoleFilterInput) {
  consoleFilterInput.addEventListener("input", (e) => renderCommandList(e.target.value));
}

function openCommand(cmd) {
  document.getElementById("args-title").textContent = cmd.Name;
  document.getElementById("args-desc").textContent = cmd.Description;
  const form = document.getElementById("args-form");
  form.innerHTML = "";

  for (const arg of cmd.Args || []) {
    const label = document.createElement("label");
    const optionalTag = arg.Optional ? " (optional)" : "";
    label.innerHTML = `<span class="label-text">${escapeHtml(arg.Name)}${optionalTag}</span>`;
    let input;
    if (arg.Choices && arg.Choices.length > 0) {
      input = document.createElement("select");
      if (arg.Optional) {
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = arg.Default ? `(default: ${arg.Default})` : "(none)";
        input.appendChild(blank);
      }
      for (const choice of arg.Choices) {
        const opt = document.createElement("option");
        opt.value = choice;
        opt.textContent = choice;
        input.appendChild(opt);
      }
    } else {
      input = document.createElement("input");
      input.type = "text";
      if (arg.Default) input.value = arg.Default;
      if (arg.Rest) input.placeholder = "space or comma separated";
    }
    input.dataset.argName = arg.Name;
    label.appendChild(input);
    form.appendChild(label);
  }

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "btn-primary";
  submit.textContent = cmd.Confirm ? "Continue" : "Run";
  form.appendChild(submit);

  form.onsubmit = (e) => {
    e.preventDefault();
    const values = Array.from(form.querySelectorAll("[data-arg-name]")).map((el) => el.value);
    if (cmd.Confirm) showConsoleConfirm(cmd, values);
    else runRegistryCommand(cmd, values);
  };

  showConsoleScreen("args");
}

function showConsoleConfirm(cmd, values) {
  document.getElementById("confirm-text").textContent = `${cmd.Name} ${values.filter(Boolean).join(" ")}`.trim();
  const input = document.getElementById("confirm-input");
  const yes = document.getElementById("confirm-yes");
  input.value = "";
  input.placeholder = cmd.Name;
  yes.disabled = true;
  input.oninput = () => { yes.disabled = input.value.trim() !== cmd.Name; };
  yes.onclick = () => runRegistryCommand(cmd, values);
  document.getElementById("confirm-no").onclick = () => showConsoleScreen("args");
  showConsoleScreen("confirm");
  setTimeout(() => input.focus(), 50);
}

function resolveLogContainer(cmd, values) {
  if (!cmd.LogContainer) return null;
  const m = /^\{(\d+)\}$/.exec(cmd.LogContainer);
  if (!m) return null;
  const idx = parseInt(m[1], 10) - 1;
  const v = values[idx];
  return v ? v : null;
}

function pathEscape(s) {
  let out = "";
  for (const ch of unescape(encodeURIComponent(s))) {
    const code = ch.charCodeAt(0);
    if (/[A-Za-z0-9\-_.~]/.test(ch)) out += ch;
    else out += "%" + code.toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}

function queryEscape(s) {
  if (s === " ") return "+";
  let out = "";
  for (const ch of unescape(encodeURIComponent(s))) {
    if (ch === " ") out += "+";
    else if (/[A-Za-z0-9\-_.~]/.test(ch)) out += ch;
    else out += "%" + ch.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}

function argValue(cmd, values, name) {
  const i = (cmd.Args || []).findIndex((a) => a.Name === name);
  return i === -1 ? "" : values[i];
}

function splitList(v) {
  const sep = v.includes(",") ? "," : " ";
  return v.split(sep).map((s) => s.trim()).filter(Boolean);
}

function prepareCommand(cmd, values) {
  let path = cmd.PathTemplate;
  values.forEach((value, i) => {
    const placeholder = `{${i + 1}}`;
    if (path.includes(placeholder)) path = path.split(placeholder).join(pathEscape(value));
  });

  if (cmd.Query && cmd.Query.length) {
    const pairs = [];
    for (const qp of cmd.Query) {
      const v = qp.ArgName ? argValue(cmd, values, qp.ArgName) : qp.Literal || "";
      if (!v) continue;
      pairs.push(`${queryEscape(qp.Key)}=${queryEscape(v)}`);
    }
    if (pairs.length) path += "?" + pairs.join("&");
  }

  let body = null;
  if (cmd.BodyMode === "json") {
    const obj = {};
    for (const bf of cmd.BodyFields || []) {
      const v = argValue(cmd, values, bf.ArgName);
      if (bf.Array) {
        if (!v) continue;
        obj[bf.Key] = splitList(v);
      } else {
        obj[bf.Key] = v;
      }
    }
    body = JSON.stringify(obj);
  }

  return { method: cmd.Method, path, body };
}

async function callApi(method, path, body) {
  const opts = { method };
  if (body !== null && body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = body;
  }
  const res = await fetch(path, opts);
  const status = res.status;
  const raw = await res.text();
  return parseApiResult(raw, status);
}

function parseApiResult(raw, status) {
  if (!raw) return { ok: status === 200, message: `(empty response, HTTP ${status})`, data: null, rawList: null };
  let parsed;
  try { parsed = JSON.parse(raw); } catch (_) { return { ok: false, message: raw, data: null, rawList: null }; }
  if (Array.isArray(parsed)) return { ok: status === 200, message: "", data: null, rawList: parsed };
  let data = parsed;
  if (data && typeof data.detail === "object" && data.detail !== null) data = data.detail;
  if (data && typeof data.message === "string") {
    const ok = typeof data.ok === "boolean" ? data.ok : status === 200;
    return { ok, message: data.message, data, rawList: null };
  }
  return { ok: status === 200, message: "", data, rawList: null };
}

async function runManualImportByIndex(cmd, values) {
  const app = values[0] || "";
  const idx = parseInt((values[1] || "").trim(), 10);
  if (Number.isNaN(idx)) throw new Error(`index must be a number, got ${JSON.stringify(values[1])}`);
  const listPath = cmd.PathTemplate.replace("{1}", pathEscape(app));
  const listRes = await callApi("GET", listPath, null);
  if (!listRes.rawList) throw new Error("expected a JSON array response");
  const item = listRes.rawList[idx];
  if (!item) throw new Error(`no candidate at index ${idx} (${listRes.rawList.length} available) — run stack-arr-import-candidates ${app} again`);
  if (!item.file) throw new Error(`candidate at index ${idx} has no 'file' field`);
  return callApi("POST", listPath, JSON.stringify(item.file));
}

async function runLogLevelsReset(values) {
  if ((values[0] || "").trim() === "reset") return callApi("POST", "/api/log-levels/reset", null);
  return callApi("GET", "/api/log-levels", null);
}

async function runLetterboxdFilmography(cmd, values) {
  const role = (values[0] || "").trim();
  const slug = (values[1] || "").trim();
  if (!role || !slug) throw new Error("both role and slug are required");
  const prepared = prepareCommand(cmd, []);
  return callApi(cmd.Method, prepared.path, JSON.stringify({ url: `https://letterboxd.com/${role}/${slug}/` }));
}

async function runLetterboxdPopular(cmd) {
  const prepared = prepareCommand(cmd, []);
  return callApi(cmd.Method, prepared.path, JSON.stringify({ url: "https://letterboxd.com/films/" }));
}

async function runImportListAdd(cmd, values) {
  const spec = cmd.BodyFields;
  const path = prepareCommand(cmd, values).path;
  const fields = {};
  for (const f of spec.Fields || []) fields[f.Key] = argValue(cmd, values, f.ArgName);
  const search = spec.SearchArg ? argValue(cmd, values, spec.SearchArg) !== "no-search" : true;
  const body = {
    implementation: spec.Implementation,
    name: spec.NameArg ? argValue(cmd, values, spec.NameArg) : spec.Name,
    fields,
    search_on_add: search,
  };
  return callApi(cmd.Method, path, JSON.stringify(body));
}

async function execCommand(cmd, values) {
  if (cmd.BodyMode === "manual-import-by-index") return runManualImportByIndex(cmd, values);
  if (cmd.BodyMode === "log-levels-reset") return runLogLevelsReset(values);
  if (cmd.BodyMode === "letterboxd-filmography") return runLetterboxdFilmography(cmd, values);
  if (cmd.BodyMode === "letterboxd-popular") return runLetterboxdPopular(cmd);
  if (cmd.BodyMode === "import-list-add") return runImportListAdd(cmd, values);
  const prepared = prepareCommand(cmd, values);
  return callApi(prepared.method, prepared.path, prepared.body);
}

async function runRegistryCommand(cmd, values) {
  showConsoleScreen("run");
  document.getElementById("run-title").textContent = cmd.Name;
  const statusEl = document.getElementById("run-status");
  statusEl.textContent = "EXECUTING";
  statusEl.className = "pending";
  document.getElementById("result-pane").textContent = "";
  logLine("pending", `${cmd.Name} — requested`);

  const container = resolveLogContainer(cmd, values);
  if (container) selectLogSource(container);

  try {
    const result = await execCommand(cmd, values);
    statusEl.textContent = result.ok ? "COMPLETE" : "FAILED";
    statusEl.className = result.ok ? "ok" : "err";
    document.getElementById("result-pane").textContent = renderConsoleResult(result);
    logLine(result.ok ? "ok" : "err", `${cmd.Name} — ${result.message || (result.ok ? "done" : "failed")}`);
  } catch (e) {
    statusEl.textContent = "REQUEST FAILED";
    statusEl.className = "err";
    document.getElementById("result-pane").textContent = String(e.message || e);
    logLine("err", `${cmd.Name} — ${e.message || e}`);
  }
}

function renderConsoleResult(result) {
  const lines = [];
  if (result.message) lines.push(result.message);
  if (result.rawList) {
    if (!result.message && result.rawList.length === 0) return "(empty list)";
    for (const item of result.rawList) lines.push("  " + summarizeConsoleItem(item));
    return lines.join("\n");
  }
  const data = result.data || {};
  for (const key of Object.keys(data).sort()) {
    if (key === "message" || key === "ok") continue;
    const v = data[key];
    if (Array.isArray(v)) {
      if (v.length === 0) continue;
      lines.push("", key + ":");
      for (const item of v) lines.push("  " + summarizeConsoleItem(item));
    } else if (v && typeof v === "object") {
      if (Object.keys(v).length === 0) continue;
      lines.push("", key + ":");
      lines.push(indentDict(v, "  "));
    } else {
      lines.push(`${key}: ${v}`);
    }
  }
  const out = lines.join("\n").trim();
  return out || "(no output)";
}

function indentDict(d, indent) {
  const lines = [];
  for (const key of Object.keys(d).sort()) {
    const v = d[key];
    if (v && typeof v === "object" && !Array.isArray(v)) {
      lines.push(indent + key + ":");
      lines.push(indentDict(v, indent + "  "));
    } else {
      lines.push(`${indent}${key}: ${JSON.stringify(v)}`);
    }
  }
  return lines.join("\n");
}

function summarizeConsoleItem(item) {
  if (item && typeof item === "object" && !Array.isArray(item)) {
    const priority = ["title", "name", "label", "message"];
    const parts = [];
    const used = new Set();
    for (const key of priority) {
      if (key in item) { parts.push(String(item[key])); used.add(key); }
    }
    for (const key of Object.keys(item).sort()) {
      if (used.has(key)) continue;
      const v = item[key];
      parts.push(typeof v === "object" ? `${key}=${JSON.stringify(v)}` : `${key}=${v}`);
    }
    return parts.join("  ");
  }
  return String(item);
}
