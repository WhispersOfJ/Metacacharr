namespace Metacache.Pages;

/// <summary>Warm schedule calendar view (#6).</summary>
public static class WarmCalendar
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Warm Calendar</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f;--bad:#e5534b;--warn:#ffb454}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font:14px/1.5 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:1000px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600}
button:hover{opacity:.85}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px}
.calendar{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-bottom:12px}
.day-header{text-align:center;color:var(--muted);font-size:11px;font-weight:600;padding:4px}
.day{background:#1c2029;border:1px solid var(--border);border-radius:6px;padding:8px;min-height:60px;font-size:12px}
.day.today{border-color:var(--accent)}
.day .date{color:var(--muted);font-size:11px;margin-bottom:4px}
.day .events{font-size:10px}
.warm-tag{display:inline-block;padding:1px 4px;border-radius:3px;font-size:9px;font-weight:600;margin:1px}
.warm-tag.ok{background:#1a3a2a;color:var(--good)}.warm-tag.fail{background:#3a1a1a;color:var(--bad)}.warm-tag.run{background:#1a2a3a;color:var(--accent)}
.status{display:flex;gap:12px;margin-bottom:12px}
.status-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;flex:1}
.status-card .label{color:var(--muted);font-size:11px;text-transform:uppercase}.status-card .value{font-size:18px;font-weight:600;margin-top:4px}
.history{margin-top:8px}
.history-row{display:flex;gap:8px;padding:6px;border-bottom:1px solid #1c2029;font-size:12px}
.history-row .time{color:var(--muted);width:140px}.history-row .source{width:80px}.history-row .result{flex:1}
</style></head><body>
<h1>📅 Warm Calendar</h1>
<div class="sub">Warm run history and schedule overview</div>
<div class="status">
<div class="status-card"><div class="label">Status</div><div class="value" id="status">—</div></div>
<div class="status-card"><div class="label">Last Run</div><div class="value" id="lastRun">—</div></div>
<div class="status-card"><div class="label">Schedule</div><div class="value" id="schedule">—</div></div>
<div class="status-card"><div class="label">Items Warmed</div><div class="value" id="totalItems">—</div></div>
</div>
<div style="display:flex;gap:8px;margin-bottom:12px">
<button onclick="warm('movies')">Warm Movies</button>
<button onclick="warm('shows')">Warm Shows</button>
<button onclick="warm('all')" style="background:var(--good)">Warm All</button>
</div>
<div id="warmMsg" style="display:none;padding:8px;border-radius:6px;font-size:13px;margin-bottom:12px"></div>
<div class="card">
<h2 style="font-size:14px;margin-bottom:8px">Recent Warm Runs</h2>
<div class="history" id="history"></div>
</div>
<script>
const runs=[];
async function poll(){
  try{
    const r=await fetch('/warm/status');const d=await r.json();
    document.getElementById('status').innerHTML=d.isRunning?'<span style="color:var(--accent)">⚡ Running</span>':'<span style="color:var(--good)">✓ Idle</span>';
    if(d.lastResult){
      document.getElementById('lastRun').innerHTML=`${d.lastResult.source} · ${d.lastResult.itemsWarmed} items · ${d.lastResult.imagesWarmed} imgs · ${d.elapsedSeconds?.toFixed(0)||'?'}s`;
      document.getElementById('totalItems').textContent=d.lastResult.itemsWarmed;
      // Add to history (dedupe by time)
      const key=d.completedAt||new Date().toISOString();
      if(!runs.find(r=>r.time===key)){runs.unshift({time:key,source:d.lastResult.source,items:d.lastResult.itemsWarmed,images:d.lastResult.imagesWarmed,errors:d.lastResult.errors,elapsed:d.lastResult.elapsedSeconds});if(runs.length>20)runs.pop()}
      renderHistory();
    }
    const pr=await fetch('/warm/progress');const p=await pr.json();
    if(p.processedItems>0){
      document.getElementById('status').innerHTML=`<span style="color:var(--accent)">⚡ ${p.percentComplete?.toFixed(0)||0}% — ${p.currentItem||''}</span>`;
    }
  }catch(e){}
}
function renderHistory(){
  document.getElementById('history').innerHTML=runs.map(r=>`<div class="history-row"><span class="time">${new Date(r.time).toLocaleString()}</span><span class="source">${r.source}</span><span class="result">${r.items} items · ${r.images} imgs${r.errors?' · <span style="color:var(--bad)">'+r.errors+' errors</span>':''} · ${r.elapsed?.toFixed(0)||'?'}s</span></div>`).join('')||'<div style="padding:16px;color:var(--muted);font-style:italic">No warm runs recorded yet</div>';
}
async function warm(scope){
  const el=document.getElementById('warmMsg');el.style.display='block';el.style.background='#1a2a3a';el.style.color='var(--accent)';el.textContent='Starting /warm/'+scope+'…';
  try{const r=await fetch('/warm/'+scope,{method:'POST'});if(r.status===409){el.textContent='Already running';return}const d=await r.json();el.style.background='#1a3a2a';el.style.color='var(--good)';el.textContent='Done: '+d.itemsWarmed+' items, '+d.imagesWarmed+' images in '+(d.elapsedSeconds?.toFixed(1)||'?')+'s';poll()}
  catch(e){el.style.background='#3a1a1a';el.style.color='var(--bad)';el.textContent='Error: '+e.message}
}
setInterval(poll,3000);poll();
</script></body></html>
""";
}
