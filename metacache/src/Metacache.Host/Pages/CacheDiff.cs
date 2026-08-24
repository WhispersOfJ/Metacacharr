namespace Metacache.Pages;

/// <summary>Cache diff view — search with inline preview (#5).</summary>
public static class CacheDiff
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Cache Browser</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f;--bad:#e5534b;--warn:#ffb454}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font:14px/1.5 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:1100px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
input[type=text]{background:#20242d;border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-size:13px;width:250px}
select{background:#20242d;border:1px solid var(--border);color:var(--text);padding:8px;border-radius:6px;font-size:13px}
button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600}
.controls{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px}
.results{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.item{background:#1c2029;border:1px solid var(--border);border-radius:8px;overflow:hidden;cursor:pointer;transition:border-color .15s}
.item:hover{border-color:var(--accent)}
.item .poster{width:100%;height:280px;background:#20242d;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:40px;overflow:hidden}
.item .poster img{width:100%;height:100%;object-fit:cover}
.item .info{padding:10px}
.item .title{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .meta{color:var(--muted);font-size:11px;margin-top:2px}
.badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600}
.badge.fresh{background:#1a3a2a;color:var(--good)}.badge.stale{background:#3a3a1a;color:var(--warn)}.badge.expired{background:#3a1a1a;color:var(--bad)}
.preview{position:fixed;top:0;right:0;width:400px;height:100vh;background:var(--card);border-left:1px solid var(--border);padding:20px;overflow-y:auto;display:none;z-index:100}
.preview.open{display:block}
.preview .close{position:absolute;top:10px;right:14px;cursor:pointer;font-size:18px;color:var(--muted)}
.preview h2{font-size:16px;margin-bottom:8px}
.preview .detail{font-size:13px;margin:4px 0}.preview .lbl{color:var(--muted);display:inline-block;width:80px}
.empty{color:var(--muted);font-style:italic;padding:40px;text-align:center}
.count{color:var(--muted);font-size:12px;margin-bottom:8px}
</style></head><body>
<h1>📚 Cache Browser</h1>
<div class="sub">Browse cached items with poster previews — click any item for details</div>
<div class="controls">
<input type="text" id="q" placeholder="Search title…" onkeydown="if(event.key==='Enter')search()">
<select id="kind"><option value="">All kinds</option><option value="movie">Movies</option><option value="show">Shows</option><option value="season">Seasons</option><option value="episode">Episodes</option></select>
<select id="fresh"><option value="">Any status</option><option value="true">Fresh only</option><option value="false">Stale only</option></select>
<button onclick="search()">Search</button>
</div>
<div class="count" id="count"></div>
<div class="results" id="results"></div>
<div class="preview" id="preview"><span class="close" onclick="closePreview()">✕</span><div id="previewContent"></div></div>
<script>
const imgBase='https://image.tmdb.org/t/p';
async function search(){
  const q=document.getElementById('q').value.trim();
  const kind=document.getElementById('kind').value;
  const fresh=document.getElementById('fresh').value;
  const params=new URLSearchParams();
  if(q)params.set('q',q);if(kind)params.set('kind',kind);if(fresh)params.set('fresh',fresh);
  params.set('limit','100');
  document.getElementById('results').innerHTML='<div class="empty">Searching…</div>';
  try{
    const r=await fetch('/admin/items?'+params);const d=await r.json();
    const items=d.items||[];
    document.getElementById('count').textContent=items.length+' of '+d.total+' items';
    if(!items.length){document.getElementById('results').innerHTML='<div class="empty">No items found</div>';return}
    document.getElementById('results').innerHTML=items.map(i=>{
      const now=new Date();const exp=i.expiresAt?new Date(i.expiresAt):null;
      const isFresh=exp&&exp>now;
      const status=isFresh?'fresh':'stale';
      const poster=i.thumb?i.thumb:'';
      return`<div class="item" onclick='showPreview(${JSON.stringify(i).replace(/'/g,"&#39;")})'><div class="poster">${poster?'<img src="'+poster+'" alt="" loading="lazy">':'🎬'}</div><div class="info"><div class="title">${i.title||'Unknown'}</div><div class="meta">${i.year||'—'} · ${i.kind} · <span class="badge ${status}">${status}</span></div></div></div>`;
    }).join('');
  }catch(e){document.getElementById('results').innerHTML='<div class="empty">Error: '+e.message+'</div>'}
}
function showPreview(i){
  const exp=i.expiresAt?new Date(i.expiresAt).toLocaleString():'—';
  const isFresh=i.expiresAt&&new Date(i.expiresAt)>new Date();
  document.getElementById('previewContent').innerHTML=`
    <h2>${i.title||'Unknown'}</h2>
    ${i.thumb?'<img src="'+i.thumb+'" style="width:100%;border-radius:8px;margin:8px 0" alt="">':''}
    <div class="detail"><span class="lbl">ID:</span> <code style="font-size:11px">${i.id}</code></div>
    <div class="detail"><span class="lbl">Kind:</span> ${i.kind}</div>
    <div class="detail"><span class="lbl">Year:</span> ${i.year||'—'}</div>
    <div class="detail"><span class="lbl">Language:</span> ${i.lang||'—'}</div>
    <div class="detail"><span class="lbl">Source:</span> ${i.sourceId||'—'}</div>
    <div class="detail"><span class="lbl">Status:</span> <span class="badge ${isFresh?'fresh':'expired'}">${isFresh?'fresh':'stale/expired'}</span></div>
    <div class="detail"><span class="lbl">Expires:</span> ${exp}</div>`;
  document.getElementById('preview').classList.add('open');
}
function closePreview(){document.getElementById('preview').classList.remove('open')}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closePreview()});
search();
</script></body></html>
""";
}
