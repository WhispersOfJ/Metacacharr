namespace Metacache.Pages;

/// <summary>Guided Fix Match panel with visual candidates (#3).</summary>
public static class MatchPanel
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Fix Match</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f;--bad:#e5534b}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font:14px/1.5 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:1000px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
input[type=text]{background:#20242d;border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-size:13px;width:300px}
button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600}
button:hover{opacity:.85}button.danger{background:var(--bad)}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px}
.candidate{display:flex;gap:12px;padding:10px;border:1px solid var(--border);border-radius:8px;margin:8px 0;cursor:pointer;transition:border-color .15s}
.candidate:hover{border-color:var(--accent)}
.candidate img{width:60px;height:90px;object-fit:cover;border-radius:4px;background:#20242d}
.candidate .info{flex:1}
.candidate .title{font-weight:600;font-size:14px}
.candidate .meta{color:var(--muted);font-size:12px;margin-top:2px}
.candidate .score{font-size:12px;color:var(--accent);margin-top:4px}
.empty{color:var(--muted);font-style:italic;padding:20px;text-align:center}
.overrides{margin-top:12px}
.override-row{display:flex;align-items:center;gap:8px;padding:8px;border-bottom:1px solid #1c2029;font-size:13px}
.override-row .key{font-family:monospace;font-size:11px;color:var(--muted);width:120px;overflow:hidden;text-overflow:ellipsis}
.override-row .target{flex:1}.override-row button{font-size:11px;padding:3px 8px}
.msg{padding:8px;border-radius:6px;font-size:13px;margin:8px 0;display:none}
.msg.ok{background:#1a3a2a;color:var(--good);display:block}.msg.fail{background:#3a1a1a;color:var(--bad);display:block}
</style></head><body>
<h1>🎯 Fix Match</h1>
<div class="sub">Search for a title and pin the correct TMDB match</div>
<div style="display:flex;gap:8px;align-items:center;margin-bottom:16px">
<input type="text" id="q" placeholder="Search title (e.g. Inception)" onkeydown="if(event.key==='Enter')search()">
<select id="kind" style="background:#20242d;border:1px solid var(--border);color:var(--text);padding:8px;border-radius:6px"><option value="movie">Movie</option><option value="tv">Show</option></select>
<button onclick="search()">Search</button>
</div>
<div id="results"></div>
<div class="card overrides">
<h2 style="font-size:14px;margin-bottom:8px">Pinned Overrides</h2>
<div id="overrideList"></div>
</div>
<script>
const imgBase='https://image.tmdb.org/t/p/w185';
function msg(id,text,type){const e=document.getElementById(id);e.textContent=text;e.className='msg '+type}
async function search(){
  const q=document.getElementById('q').value.trim();if(!q)return;
  const kind=document.getElementById('kind').value;
  document.getElementById('results').innerHTML='<div class="empty">Searching…</div>';
  try{
    const r=await fetch('/library/metadata/matches',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({type:kind==='movie'?1:2,title:q,manual:1})});
    const d=await r.json();
    const items=d.Metadata||[];
    document.getElementById('results').innerHTML=items.length?items.map((m,i)=>`
      <div class="candidate" onclick="pin('${m.ratingKey}','${m.title?.replace(/'/g,"\\'")}',${m.year||0})">
        ${m.art?`<img src="${m.art}" alt="">`:'<div style="width:60px;height:90px;background:#20242d;border-radius:4px"></div>'}
        <div class="info"><div class="title">${m.title||'Unknown'}</div><div class="meta">${m.year||''} · ${m.ratingKey}</div>
        <div class="score">Score: ${(m.score*100).toFixed(0)}%</div></div>
      </div>`).join(''):'<div class="empty">No results found</div>';
  }catch(e){document.getElementById('results').innerHTML='<div class="empty">Error: '+e.message+'</div>'}
}
async function pin(key,title,year){
  const kind=document.getElementById('kind').value;
  try{
    const r=await fetch('/admin/overrides',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kind,target:'tmdb-'+key.replace('tmdb-',''),notes:'Pinned via Fix Match UI'})});
    if(r.ok){msg('results','Pinned: '+title+' ('+year+')','ok');loadOverrides()}
    else{msg('results','Failed to pin','fail')}
  }catch(e){msg('results','Error: '+e.message,'fail')}
}
async function loadOverrides(){
  try{
    const r=await fetch('/admin/overrides');const d=await r.json();
    const el=document.getElementById('overrideList');
    el.innerHTML=d.length?d.map(o=>`<div class="override-row"><span class="key" title="${o.key}">${o.key}</span><span class="target">${o.target}</span><button class="danger" onclick="del('${o.key}')">Remove</button></div>`).join(''):'<div class="empty">No overrides pinned yet</div>';
  }catch(e){}
}
async function del(key){
  try{await fetch('/admin/overrides/'+encodeURIComponent(key),{method:'DELETE'});loadOverrides()}catch(e){}
}
loadOverrides();
</script></body></html>
""";
}
