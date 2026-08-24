namespace Metacache.Pages;

/// <summary>Match override editor (#9).</summary>
public static class OverrideEditor
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Override Editor</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f;--bad:#e5534b}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font:14px/1.5 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:900px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
input[type=text]{background:#20242d;border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-size:13px}
select{background:#20242d;border:1px solid var(--border);color:var(--text);padding:8px;border-radius:6px;font-size:13px}
button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600}
button:hover{opacity:.85}button.danger{background:var(--bad)}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px}
.override-card{display:flex;align-items:center;gap:12px;padding:12px;border:1px solid var(--border);border-radius:8px;margin:8px 0;transition:border-color .15s}
.override-card:hover{border-color:var(--accent)}
.override-card .icon{font-size:24px}
.override-card .info{flex:1}
.override-card .title{font-weight:600;font-size:14px}
.override-card .meta{color:var(--muted);font-size:12px;margin-top:2px}
.override-card .notes{color:var(--muted);font-size:11px;margin-top:4px;font-style:italic}
.override-card button{font-size:11px;padding:4px 10px}
.empty{color:var(--muted);font-style:italic;padding:20px;text-align:center}
.form-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.unmatched-card{display:flex;align-items:center;gap:10px;padding:10px;border:1px solid #3a2a1a;border-radius:8px;margin:6px 0;background:#1a1510}
.unmatched-card .info{flex:1}.unmatched-card .title{font-size:13px}
.unmatched-card .hint{color:var(--muted);font-size:11px}
.unmatched-card button{font-size:11px;padding:3px 8px;background:var(--good);color:#fff}
.msg{padding:8px;border-radius:6px;font-size:13px;margin:8px 0;display:none}
.msg.ok{background:#1a3a2a;color:var(--good);display:block}
</style></head><body>
<h1>📌 Override Editor</h1>
<div class="sub">Pin match overrides and review unmatched items</div>

<div class="card">
<h2 style="font-size:14px;margin-bottom:8px">Add Override</h2>
<div class="form-row">
<select id="kind"><option value="movie">Movie</option><option value="show">Show</option></select>
<input type="text" id="target" placeholder="tmdb-movie-550" style="width:200px">
<input type="text" id="notes" placeholder="Notes (optional)" style="width:200px">
<button onclick="add()">Pin</button>
</div>
<div id="addMsg" class="msg"></div>
</div>

<div class="card">
<h2 style="font-size:14px;margin-bottom:8px">Pinned Overrides</h2>
<div id="overrideList"></div>
</div>

<div class="card">
<h2 style="font-size:14px;margin-bottom:8px">Unmatched Items</h2>
<p style="color:var(--muted);font-size:12px;margin-bottom:8px">Items with zero search results — pin them to fix future matches</p>
<div id="unmatchedList"></div>
</div>

<script>
async function load(){
  try{
    const r=await fetch('/admin/overrides');const d=await r.json();
    const el=document.getElementById('overrideList');
    el.innerHTML=d.length?d.map(o=>`<div class="override-card"><div class="icon">📌</div><div class="info"><div class="title">${o.target||o.key}</div><div class="meta">Key: <code>${o.key}</code> · Kind: ${o.kind||'—'}</div>${o.notes?'<div class="notes">'+o.notes+'</div>':''}</div><button class="danger" onclick="del('${o.key}')">Remove</button></div>`).join(''):'<div class="empty">No overrides pinned yet</div>';
  }catch(e){}

  try{
    const r=await fetch('/admin/unmatched');const d=await r.json();
    const el=document.getElementById('unmatchedList');
    el.innerHTML=d.length?d.map(u=>`<div class="unmatched-card"><div class="info"><div class="title">${u.title||'Unknown'} (${u.year||'?'})</div><div class="hint">Kind: ${u.kind} · Title: ${u.title}</div></div><button onclick="pinUnmatched('${u.key}','${u.kind}')">Pin</button></div>`).join(''):'<div class="empty">No unmatched items — all matches found!</div>';
  }catch(e){}
}

async function add(){
  const kind=document.getElementById('kind').value;
  const target=document.getElementById('target').value.trim();
  const notes=document.getElementById('notes').value.trim();
  if(!target){return}
  const el=document.getElementById('addMsg');
  try{
    const r=await fetch('/admin/overrides',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kind,target,notes:notes||null})});
    if(r.ok){el.className='msg ok';el.textContent='✓ Pinned: '+target;load()}
    else{el.className='msg';const d=await r.json();el.textContent='Error: '+(d.error||r.status)}
  }catch(e){el.className='msg';el.textContent='Error: '+e.message}
}

async function del(key){
  try{await fetch('/admin/overrides/'+encodeURIComponent(key),{method:'DELETE'});load()}catch(e){}
}

async function pinUnmatched(key,kind){
  try{
    const r=await fetch('/admin/unmatched/'+encodeURIComponent(key)+'/pin',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kind,target:key,notes:'Pinned from unmatched'})});
    if(r.ok)load();
  }catch(e){}
}

load();
</script></body></html>
""";
}
