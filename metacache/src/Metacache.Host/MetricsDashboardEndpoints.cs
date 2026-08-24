using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;

namespace Metacache.Host;

/// <summary>
/// Interactive metrics dashboard: a self-contained page at GET /dashboard with tabs
/// for live metrics, item search, cache management (purge/TTL controls), and warm
/// status. Zero external assets, works with the WAN down.
/// </summary>
public static class MetricsDashboardEndpoints
{
    public static void MapMetricsDashboard(this WebApplication app) =>
        app.MapGet("/dashboard", () => Results.Content(DashboardHtml, "text/html; charset=utf-8"));

    private const string DashboardHtml = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Metacache · Dashboard</title>
<style>
  :root { --bg:#0f1115; --card:#171a21; --border:#232833; --text:#e6e8ee; --muted:#9aa2b1; --accent:#4f8cff; --good:#3fb97f; --bad:#e5534b; --warn:#ffb454; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font:14px/1.5 ui-sans-serif, system-ui, sans-serif; padding:20px; max-width:1200px; margin:0 auto; }
  header { display:flex; align-items:baseline; gap:14px; margin-bottom:16px; flex-wrap:wrap; }
  h1 { font-size:20px; }
  #updated { color:var(--muted); font-size:12px; }
  .tabs { display:flex; gap:2px; margin-bottom:16px; border-bottom:1px solid var(--border); }
  .tab { padding:8px 16px; cursor:pointer; color:var(--muted); border-bottom:2px solid transparent; transition:all .15s; }
  .tab:hover { color:var(--text); }
  .tab.active { color:var(--accent); border-bottom-color:var(--accent); }
  .panel { display:none; }
  .panel.active { display:block; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin-bottom:12px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px; }
  .card .label { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }
  .card .value { font-size:22px; font-weight:650; margin-top:4px; }
  .rate { font-size:34px; }
  #hitRate.good { color:var(--good); } #hitRate.bad { color:var(--bad); }
  .two { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
  canvas { width:100%; height:140px; display:block; }
  .bar-row { display:flex; align-items:center; gap:10px; margin:6px 0; }
  .bar-row .name { width:80px; color:var(--muted); text-transform:capitalize; font-size:13px; }
  .bar-track { flex:1; background:#20242d; border-radius:4px; height:12px; overflow:hidden; }
  .bar-fill { height:100%; background:var(--accent); border-radius:4px; }
  .bar-row .num { width:34px; text-align:right; font-weight:600; font-size:13px; }
  .empty { color:var(--muted); font-style:italic; font-size:13px; }
  .legend { float:right; font-weight:400; text-transform:none; letter-spacing:0; font-size:11px; }
  .legend i { display:inline-block; width:8px; height:8px; border-radius:2px; margin:0 3px 0 8px; vertical-align:-1px; }
  /* Forms */
  .form-row { display:flex; gap:8px; align-items:center; margin-bottom:10px; flex-wrap:wrap; }
  .form-row label { color:var(--muted); font-size:12px; white-space:nowrap; }
  input[type=text], input[type=number], select { background:#20242d; border:1px solid var(--border); color:var(--text); padding:6px 10px; border-radius:6px; font-size:13px; outline:none; }
  input:focus, select:focus { border-color:var(--accent); }
  button { background:var(--accent); color:#fff; border:none; padding:6px 14px; border-radius:6px; font-size:13px; cursor:pointer; font-weight:600; }
  button:hover { opacity:.85; }
  button.danger { background:var(--bad); }
  button.secondary { background:var(--border); color:var(--text); }
  /* Table */
  .table-wrap { overflow-x:auto; margin-top:8px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:var(--muted); font-weight:500; padding:6px 8px; border-bottom:1px solid var(--border); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
  td { padding:5px 8px; border-bottom:1px solid #1c2029; }
  tr:hover td { background:#1a1e28; }
  .badge { display:inline-block; padding:1px 6px; border-radius:4px; font-size:11px; font-weight:600; }
  .badge.fresh { background:#1a3a2a; color:var(--good); }
  .badge.stale { background:#3a2a1a; color:var(--warn); }
  /* Warm status */
  .warm-status { display:flex; gap:12px; align-items:center; margin:10px 0; }
  .warm-dot { width:10px; height:10px; border-radius:50%; }
  .warm-dot.running { background:var(--accent); animation:pulse 1s infinite; }
  .warm-dot.idle { background:var(--muted); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .warm-result { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:12px; margin-top:8px; font-size:13px; }
  .warm-result code { background:#20242d; padding:2px 6px; border-radius:3px; font-size:12px; }
  .log { background:#0c0e12; border:1px solid var(--border); border-radius:6px; padding:10px; max-height:200px; overflow-y:auto; font-family:ui-monospace,monospace; font-size:12px; line-height:1.6; color:var(--muted); margin-top:8px; }
  .log .info { color:var(--accent); }
  .log .ok { color:var(--good); }
  .log .err { color:var(--bad); }
  @media (max-width:720px){ .two { grid-template-columns:1fr; } }
</style>
</head>
<body>
<header>
  <h1>Metacache · Dashboard</h1>
  <span id="updated">—</span>
</header>

<div class="tabs">
  <div class="tab active" data-tab="metrics">Metrics</div>
  <div class="tab" data-tab="items">Items</div>
  <div class="tab" data-tab="cache">Cache</div>
  <div class="tab" data-tab="warm">Warm</div>
</div>

<!-- ========= METRICS TAB ========= -->
<div class="panel active" id="panel-metrics">
<div class="grid">
  <div class="card"><div class="label">Hit rate</div><div class="value rate" id="hitRate">–</div></div>
  <div class="card"><div class="label">Requests</div><div class="value" id="requests">–</div></div>
  <div class="card"><div class="label">Cache hits</div><div class="value" id="hits">–</div></div>
  <div class="card"><div class="label">Misses</div><div class="value" id="misses">–</div></div>
  <div class="card"><div class="label">Upstream entries</div><div class="value" id="upstreamEntries">–</div></div>
  <div class="card"><div class="label">Cached items</div><div class="value" id="itemEntries">–</div></div>
</div>
<div class="two">
  <div class="card">
    <div class="label">Hit rate — live vs Prometheus <span class="legend"><i style="background:#4f8cff"></i>live<i style="background:#ffb454"></i>scrapes</span></div>
    <canvas id="spark"></canvas>
  </div>
  <div class="card">
    <div class="label">Items by kind</div>
    <div id="kinds"></div>
  </div>
</div>
<div class="grid">
  <div class="card"><div class="label">Image files</div><div class="value" id="imageFiles">–</div></div>
  <div class="card"><div class="label">Image bytes</div><div class="value" id="imageBytes">–</div></div>
  <div class="card"><div class="label">Upstream bytes</div><div class="value" id="upstreamBytes">–</div></div>
  <div class="card"><div class="label">Database size</div><div class="value" id="dbBytes">–</div></div>
</div>
</div>

<!-- ========= ITEMS TAB ========= -->
<div class="panel" id="panel-items">
<div class="card">
  <div class="label">Search cached items</div>
  <div class="form-row" style="margin-top:10px">
    <label>Title:</label>
    <input type="text" id="itemQ" placeholder="e.g. Inception" style="width:200px">
    <label>Kind:</label>
    <select id="itemKind"><option value="">all</option><option value="movie">movie</option><option value="show">show</option><option value="season">season</option><option value="episode">episode</option></select>
    <label>Fresh:</label>
    <select id="itemFresh"><option value="">any</option><option value="true">yes</option><option value="false">no</option></select>
    <button onclick="searchItems()">Search</button>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>ID</th><th>Kind</th><th>Title</th><th>Year</th><th>Source</th><th>Status</th><th>Expires</th></tr></thead>
      <tbody id="itemResults"><tr><td colspan="7" class="empty">Enter a search term and click Search</td></tr></tbody>
    </table>
  </div>
  <div id="itemCount" style="color:var(--muted);font-size:12px;margin-top:6px"></div>
</div>
</div>

<!-- ========= CACHE TAB ========= -->
<div class="panel" id="panel-cache">
<div class="two">
  <div class="card">
    <div class="label">Database info</div>
    <div id="dbInfo" style="margin-top:8px;font-size:13px"></div>
  </div>
  <div class="card">
    <div class="label">Purge controls</div>
    <div style="margin-top:8px">
      <button class="danger" onclick="purgeExpired()">Purge expired entries</button>
      <button class="secondary" onclick="purgeAll()" style="margin-left:6px">Purge all upstream</button>
      <div id="purgeResult" style="margin-top:8px;font-size:13px"></div>
    </div>
  </div>
</div>
<div class="card" style="margin-top:10px">
  <div class="label">Upstream cache entries (eviction candidates)</div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Hash</th><th>URL</th><th>Size</th><th>Stored</th></tr></thead>
      <tbody id="upstreamEntries"><tr><td colspan="4" class="empty">Loading…</td></tr></tbody>
    </table>
  </div>
</div>
</div>

<!-- ========= WARM TAB ========= -->
<div class="panel" id="panel-warm">
<div class="card">
  <div class="label">Warm controls</div>
  <div style="margin-top:10px">
    <button onclick="warm('movies')">Warm movies (Radarr)</button>
    <button onclick="warm('shows')" style="margin-left:6px">Warm shows (Sonarr)</button>
    <button onclick="warm('all')" style="margin-left:6px">Warm all</button>
  </div>
  <div class="warm-status" id="warmStatus"></div>
  <div id="warmResult"></div>
</div>
<div class="card" style="margin-top:10px">
  <div class="label">Warm log</div>
  <div class="log" id="warmLog">No warm runs yet.</div>
</div>
</div>

<script>
// ====== Tab switching ======
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('panel-' + t.dataset.tab).classList.add('active');
    if (t.dataset.tab === 'cache') loadCache();
    if (t.dataset.tab === 'warm') pollWarm();
  });
});

// ====== Helpers ======
function humanize(b) {
  if (b == null) return "–";
  if (b < 1024) return b + " B";
  const u = ["KB","MB","GB","TB"]; let i = -1;
  do { b /= 1024; i++; } while (b >= 1024 && i < u.length - 1);
  return b.toFixed(1) + " " + u[i];
}
function set(id, t) { const e = document.getElementById(id); if (e) e.textContent = t; }
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ====== Metrics ======
const MAX = 120;
let history = [], scrape = [];
const kc = { movie:"#4f8cff", show:"#a06bff", season:"#ffb454", episode:"#3fb97f" };

function renderKinds(m) {
  const el = document.getElementById("kinds"); el.innerHTML = "";
  const kinds = m.itemsByKind || {};
  const entries = Object.entries(kinds);
  if (!entries.length) { el.innerHTML = '<div class="empty">nothing warmed yet</div>'; return; }
  const total = entries.reduce((a,b) => a + b[1], 0) || 1;
  for (const [k, c] of entries) {
    const r = document.createElement("div"); r.className = "bar-row";
    r.innerHTML = `<span class="name">${esc(k)}</span><div class="bar-track"><div class="bar-fill" style="width:${c/total*100}%;background:${kc[k]||'#4f8cff'}"></div></div><span class="num">${c}</span>`;
    el.appendChild(r);
  }
}

function draw() {
  const c = document.getElementById("spark"), dpr = devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  c.width = w*dpr; c.height = h*dpr;
  const ctx = c.getContext("2d"); ctx.scale(dpr,dpr); ctx.clearRect(0,0,w,h);
  if (scrape.length > 1) {
    ctx.strokeStyle = "rgba(255,180,84,0.75)"; ctx.lineWidth = 1.5; ctx.beginPath();
    for (let i = 0; i < scrape.length; i++) { const x = i/(scrape.length-1)*w, y = h - scrape[i].hitRate*h; i ? ctx.lineTo(x,y) : ctx.moveTo(x,y); }
    ctx.stroke();
  }
  if (!history.length) return;
  ctx.strokeStyle = "#4f8cff"; ctx.lineWidth = 2; ctx.beginPath();
  for (let i = 0; i < history.length; i++) { const x = i/(MAX-1)*w, y = h - history[i]*h; i ? ctx.lineTo(x,y) : ctx.moveTo(x,y); }
  ctx.stroke();
}

async function pollMetrics() {
  try {
    const r = await fetch("/metrics"); if (!r.ok) throw new Error("HTTP "+r.status);
    const m = await r.json();
    set("hitRate", (m.hitRate*100).toFixed(1)+"%");
    document.getElementById("hitRate").className = "value rate " + (m.hitRate >= 0.9 ? "good" : m.hitRate < 0.5 ? "bad" : "");
    set("requests", m.requests); set("hits", m.hits); set("misses", m.misses);
    set("upstreamEntries", m.upstreamEntries); set("itemEntries", m.itemEntries);
    set("imageFiles", m.images.files); set("imageBytes", humanize(m.images.bytes));
    set("upstreamBytes", humanize(m.upstreamBytes)); set("dbBytes", humanize(m.dbBytes));
    renderKinds(m);
    history.push(m.hitRate); if (history.length > MAX) history.shift();
    scrape = m.scrapeHistory || []; draw();
    set("updated", "updated " + new Date().toLocaleTimeString());
  } catch(e) { set("updated", "error: " + e.message); }
}

// ====== Items ======
async function searchItems() {
  const q = document.getElementById("itemQ").value.trim();
  const kind = document.getElementById("itemKind").value;
  const fresh = document.getElementById("itemFresh").value;
  const params = new URLSearchParams();
  if (q) params.set("q", q); if (kind) params.set("kind", kind); if (fresh) params.set("fresh", fresh);
  params.set("limit", "100");
  const tbody = document.getElementById("itemResults");
  try {
    const r = await fetch("/admin/items?" + params);
    const data = await r.json();
    tbody.innerHTML = "";
    if (!data.items.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty">No items found</td></tr>'; }
    for (const i of data.items) {
      const fresh = i.expiresAt > new Date().toISOString();
      const tr = document.createElement("tr");
      tr.innerHTML = `<td style="font-family:monospace;font-size:11px">${esc(i.id)}</td><td>${esc(i.kind)}</td><td>${esc(i.title||'–')}</td><td>${i.year||'–'}</td><td>${esc(i.sourceId||'–')}</td><td><span class="badge ${fresh?'fresh':'stale'}">${fresh?'fresh':'stale'}</span></td><td style="font-size:11px">${i.expiresAt ? new Date(i.expiresAt).toLocaleDateString() : '–'}</td>`;
      tbody.appendChild(tr);
    }
    set("itemCount", `${data.items.length} of ${data.total} items`);
  } catch(e) { tbody.innerHTML = `<tr><td colspan="7" class="empty">Error: ${esc(e.message)}</td></tr>`; }
}
document.getElementById("itemQ").addEventListener("keydown", e => { if (e.key === "Enter") searchItems(); });

// ====== Cache ======
async function loadCache() {
  try {
    const [dbR, upR] = await Promise.all([fetch("/admin/database"), fetch("/admin/upstream?limit=20")]);
    const db = await dbR.json();
    document.getElementById("dbInfo").innerHTML = `
      <div>Upstream entries: <b>${db.upstreamEntries}</b></div>
      <div>Cached items: <b>${db.itemEntries}</b></div>
      <div>URL entries: <b>${db.urlEntries}</b></div>
      <div>Upstream bytes: <b>${humanize(db.upstreamBytes)}</b></div>
      <div>Image bytes: <b>${humanize(db.imageBytes)}</b></div>`;
    const up = await upR.json();
    const tbody = document.getElementById("upstreamEntries"); tbody.innerHTML = "";
    if (!up.evictionCandidates.length) { tbody.innerHTML = '<tr><td colspan="4" class="empty">No entries</td></tr>'; }
    for (const e of up.evictionCandidates) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td style="font-family:monospace;font-size:11px">${esc(e.hash?.slice(0,12))}…</td><td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(e.url)}">${esc(e.url)}</td><td>${humanize(e.size)}</td><td style="font-size:11px">${new Date(e.fetchedAt).toLocaleString()}</td>`;
      tbody.appendChild(tr);
    }
  } catch(e) { document.getElementById("dbInfo").textContent = "Error: " + e.message; }
}

async function purgeExpired() {
  const el = document.getElementById("purgeResult");
  try {
    const r = await fetch("/admin/purge/selective", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({expired:true}) });
    const d = await r.json();
    el.innerHTML = `<span class="ok">Purged ${d.removed} expired entries</span>`;
    loadCache();
  } catch(e) { el.innerHTML = `<span class="err">Error: ${esc(e.message)}</span>`; }
}

async function purgeAll() {
  if (!confirm("Delete ALL upstream cache entries? Items and images are kept.")) return;
  const el = document.getElementById("purgeResult");
  try {
    const r = await fetch("/admin/purge/selective", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({expired:true, imageBytes:0}) });
    const d = await r.json();
    el.innerHTML = `<span class="ok">Purged ${d.removed} entries</span>`;
    loadCache();
  } catch(e) { el.innerHTML = `<span class="err">Error: ${esc(e.message)}</span>`; }
}

// ====== Warm ======
let warmRunning = false;
async function warm(scope) {
  const log = document.getElementById("warmLog");
  log.innerHTML = `<div class="info">Starting /warm/${scope}…</div>`;
  document.getElementById("warmResult").innerHTML = "";
  try {
    const r = await fetch("/warm/" + scope, { method:"POST" });
    if (r.status === 409) { log.innerHTML += `<div class="err">Already running — wait for current warm to finish</div>`; return; }
    const d = await r.json();
    warmRunning = false;
    const html = `<div class="ok">Done in ${d.elapsedSeconds?.toFixed(1)||'?'}s</div>
      <div>Items warmed: <b>${d.itemsWarmed||0}</b> · Images: <b>${d.imagesWarmed||0}</b> · Missing: <b>${d.missing||0}</b> · Errors: <b>${d.errors||0}</b></div>`;
    document.getElementById("warmResult").innerHTML = `<div class="warm-result">${html}</div>`;
    log.innerHTML += `<div class="ok">✓ ${scope} complete — ${d.itemsWarmed||0} items, ${d.imagesWarmed||0} images</div>`;
    pollMetrics();
  } catch(e) { log.innerHTML += `<div class="err">Error: ${esc(e.message)}</div>`; }
}

async function pollWarm() {
  try {
    const r = await fetch("/warm/status");
    const d = await r.json();
    warmRunning = d.isRunning;
    const el = document.getElementById("warmStatus");
    el.innerHTML = `<div class="warm-dot ${d.isRunning?'running':'idle'}"></div><span>${d.isRunning ? 'Warm in progress…' : 'Idle'}</span>`;
    if (d.lastResult) {
      document.getElementById("warmResult").innerHTML = `<div class="warm-result">
        Last run: <b>${d.lastResult.source}</b> — items: ${d.lastResult.itemsWarmed}, images: ${d.lastResult.imagesWarmed}, errors: ${d.lastResult.errors}, elapsed: ${d.lastResult.elapsedSeconds?.toFixed(1)||'?'}s</div>`;
    }
  } catch(e) {}
}

// ====== Init ======
setInterval(pollMetrics, 3000);
pollMetrics();
</script>
</body>
</html>
""";
}
