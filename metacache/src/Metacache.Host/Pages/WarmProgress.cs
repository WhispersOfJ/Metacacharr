namespace Metacache.Pages;

/// <summary>Real-time warm progress bar with ETA (#2).</summary>
public static class WarmProgress
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Warm Progress</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f;--bad:#e5534b}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font:14px/1.6 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:900px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600}
button:hover{opacity:.85}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px}
.progress-container{margin:16px 0}
.progress-bar{width:100%;height:24px;background:#20242d;border-radius:12px;overflow:hidden;position:relative}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--good));border-radius:12px;transition:width .3s ease}
.progress-text{position:absolute;top:0;left:0;right:0;text-align:center;line-height:24px;font-size:12px;font-weight:600;color:#fff}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}
.stat{background:#20242d;border-radius:8px;padding:10px;text-align:center}
.stat .num{font-size:20px;font-weight:700}.stat .lbl{color:var(--muted);font-size:10px;text-transform:uppercase}
.current{margin:8px 0;padding:8px 12px;background:#20242d;border-radius:6px;font-size:13px}
.current .label{color:var(--muted);font-size:11px}
.log{background:#0c0e12;border:1px solid var(--border);border-radius:6px;padding:10px;max-height:200px;overflow-y:auto;font-family:ui-monospace,monospace;font-size:11px;line-height:1.6;color:var(--muted);margin-top:8px}
.log .info{color:var(--accent)}.log .ok{color:var(--good)}.log .err{color:var(--bad)}
.controls{display:flex;gap:8px;margin-bottom:12px}
.idle-msg{color:var(--muted);font-style:italic;text-align:center;padding:40px;font-size:15px}
</style></head><body>
<h1>⚡ Warm Progress</h1>
<div class="sub">Real-time progress bar with ETA — polls /warm/progress every 1s</div>
<div class="controls">
<button onclick="warm('movies')">Warm Movies</button>
<button onclick="warm('shows')">Warm Shows</button>
<button onclick="warm('all')">Warm All</button>
</div>
<div class="card" id="progressCard">
<div class="idle-msg" id="idleMsg">No warm in progress — click a button above to start</div>
<div id="activeProgress" style="display:none">
<div class="progress-container">
<div class="progress-bar"><div class="progress-fill" id="bar" style="width:0%"></div><div class="progress-text" id="barText">0%</div></div>
</div>
<div class="stats">
<div class="stat"><div class="num" id="processed">0</div><div class="lbl">Processed</div></div>
<div class="stat"><div class="num" id="total">0</div><div class="lbl">Total</div></div>
<div class="stat"><div class="num" id="images">0</div><div class="lbl">Images</div></div>
<div class="stat"><div class="num" id="errors">0</div><div class="lbl">Errors</div></div>
</div>
<div class="current"><div class="label">Currently warming:</div><div id="currentItem" style="margin-top:4px">—</div></div>
<div style="display:flex;gap:16px;font-size:13px;color:var(--muted);margin-top:8px">
<span>Elapsed: <b id="elapsed">0s</b></span>
<span>ETA: <b id="eta">calculating…</b></span>
<span>Speed: <b id="speed">—</b></span>
</div>
</div>
</div>
<div class="card">
<h2 style="font-size:14px;margin-bottom:8px">Activity Log</h2>
<div class="log" id="log">Waiting for warm to start…</div>
</div>
<script>
const logEl=document.getElementById('log');
function addLog(msg,cls){const d=document.createElement('div');d.className=cls||'';d.textContent=new Date().toLocaleTimeString()+' '+msg;logEl.appendChild(d);logEl.scrollTop=logEl.scrollHeight}
function fmt(s){if(s==null)return'—';if(s<60)return s.toFixed(0)+'s';return Math.floor(s/60)+'m '+(s%60).toFixed(0)+'s'}
async function poll(){
  try{
    const r=await fetch('/warm/progress');
    const d=await r.json();
    if(d.processedItems>0&&d.totalItems>0){
      document.getElementById('idleMsg').style.display='none';
      document.getElementById('activeProgress').style.display='block';
      const pct=Math.min(100,d.percentComplete||0);
      document.getElementById('bar').style.width=pct+'%';
      document.getElementById('barText').textContent=pct.toFixed(1)+'%';
      document.getElementById('processed').textContent=d.processedItems;
      document.getElementById('total').textContent=d.totalItems;
      document.getElementById('images').textContent=d.imagesWarmed;
      document.getElementById('errors').textContent=d.errors;
      document.getElementById('currentItem').textContent=d.currentItem||'—';
      document.getElementById('elapsed').textContent=fmt(d.elapsedSeconds);
      document.getElementById('eta').textContent=fmt(d.estimatedRemainingSeconds);
      const speed=d.elapsedSeconds>0?(d.processedItems/d.elapsedSeconds).toFixed(1):'—';
      document.getElementById('speed').textContent=speed+' items/s';
    }else{
      const sr=await fetch('/warm/status');const s=await sr.json();
      if(!s.isRunning){document.getElementById('idleMsg').style.display='block';document.getElementById('activeProgress').style.display='none'}
    }
  }catch(e){}
}
async function warm(scope){
  addLog('Starting /warm/'+scope+'…','info');
  try{const r=await fetch('/warm/'+scope,{method:'POST'});if(r.status===409){addLog('Already running','err');return}const d=await r.json();addLog('Done: '+d.itemsWarmed+' items, '+d.imagesWarmed+' images in '+(d.elapsedSeconds?.toFixed(1)||'?')+'s','ok')}
  catch(e){addLog('Error: '+e.message,'err')}
}
setInterval(poll,1000);poll();
</script></body></html>
""";
}
