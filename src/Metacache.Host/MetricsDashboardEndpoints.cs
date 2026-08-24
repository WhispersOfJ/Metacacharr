using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;

namespace Metacache.Host;

/// <summary>
/// Minimal metrics dashboard (M3): a self-contained page at GET /dashboard that
/// polls <see cref="MetricsEndpoints"/>' /metrics every 3 s and renders the hit
/// rate, request counters, per-kind item counts, and disk usage — with a live
/// hit-rate sparkline. Zero external assets, so it works with the WAN down.
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
<title>Metacache · Cache metrics</title>
<style>
  :root { --bg:#0f1115; --card:#171a21; --border:#232833; --text:#e6e8ee; --muted:#9aa2b1; --accent:#4f8cff; --good:#3fb97f; --bad:#e5534b; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font:14px/1.5 ui-sans-serif, system-ui, sans-serif; padding:24px; max-width:1100px; margin:0 auto; }
  header { display:flex; align-items:baseline; gap:14px; margin-bottom:20px; flex-wrap:wrap; }
  h1 { font-size:20px; }
  #updated { color:var(--muted); font-size:12px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:14px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px; }
  .card .label { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }
  .card .value { font-size:22px; font-weight:650; margin-top:4px; }
  .rate { font-size:34px; }
  #hitRate.good { color:var(--good); } #hitRate.bad { color:var(--bad); }
  .two { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:14px; }
  canvas { width:100%; height:150px; display:block; }
  .bar-row { display:flex; align-items:center; gap:10px; margin:7px 0; }
  .bar-row .name { width:80px; color:var(--muted); text-transform:capitalize; }
  .bar-track { flex:1; background:#20242d; border-radius:5px; height:14px; overflow:hidden; }
  .bar-fill { height:100%; background:var(--accent); border-radius:5px; }
  .bar-row .num { width:34px; text-align:right; font-weight:650; }
  .empty { color:var(--muted); font-style:italic; }
  @media (max-width:720px){ .two { grid-template-columns:1fr; } }
</style>
</head>
<body>
<header>
  <h1>Metacache · Cache metrics</h1>
  <span id="updated">—</span>
</header>
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
    <div class="label">Hit rate history (last 120 polls)</div>
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
<script>
const MAX = 120;
let history = [];
const kindColors = { movie: "#4f8cff", show: "#a06bff", season: "#ffb454", episode: "#3fb97f" };

function humanize(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return bytes + " B";
  const units = ["KB", "MB", "GB", "TB"];
  let i = -1;
  do { bytes /= 1024; i++; } while (bytes >= 1024 && i < units.length - 1);
  return bytes.toFixed(1) + " " + units[i];
}

function set(id, text) { document.getElementById(id).textContent = text; }

function renderKinds(m) {
  const el = document.getElementById("kinds");
  el.innerHTML = "";
  const kinds = m.itemsByKind || {};
  const entries = Object.entries(kinds);
  if (!entries.length) { el.innerHTML = '<div class="empty">nothing warmed yet — try POST /warm/all</div>'; return; }
  const total = entries.reduce((a, b) => a + b[1], 0) || 1;
  for (const [kind, count] of entries) {
    const row = document.createElement("div"); row.className = "bar-row";
    const name = document.createElement("span"); name.className = "name"; name.textContent = kind;
    const track = document.createElement("div"); track.className = "bar-track";
    const fill = document.createElement("div"); fill.className = "bar-fill";
    fill.style.width = (count / total * 100) + "%";
    fill.style.background = kindColors[kind] || "#4f8cff";
    track.appendChild(fill);
    const num = document.createElement("span"); num.className = "num"; num.textContent = count;
    row.append(name, track, num);
    el.appendChild(row);
  }
}

function draw() {
  const c = document.getElementById("spark");
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  c.width = w * dpr; c.height = h * dpr;
  const ctx = c.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  if (!history.length) return;
  ctx.strokeStyle = "#4f8cff"; ctx.lineWidth = 2;
  ctx.beginPath();
  for (let i = 0; i < history.length; i++) {
    const x = (i / (MAX - 1)) * w;
    const y = h - history[i] * h;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();
}

async function poll() {
  try {
    const r = await fetch("/metrics");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const m = await r.json();
    set("hitRate", (m.hitRate * 100).toFixed(1) + "%");
    document.getElementById("hitRate").className = "value rate " + (m.hitRate >= 0.9 ? "good" : m.hitRate < 0.5 ? "bad" : "");
    set("requests", m.requests);
    set("hits", m.hits);
    set("misses", m.misses);
    set("upstreamEntries", m.upstreamEntries);
    set("itemEntries", m.itemEntries);
    set("imageFiles", m.images.files);
    set("imageBytes", humanize(m.images.bytes));
    set("upstreamBytes", humanize(m.upstreamBytes));
    set("dbBytes", humanize(m.dbBytes));
    renderKinds(m);
    history.push(m.hitRate);
    if (history.length > MAX) history.shift();
    draw();
    set("updated", "updated " + new Date().toLocaleTimeString());
  } catch (e) {
    set("updated", "error: " + e.message);
  }
}

setInterval(poll, 3000);
poll();
</script>
</body>
</html>
""";
}
