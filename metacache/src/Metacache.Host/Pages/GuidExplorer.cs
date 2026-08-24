namespace Metacache.Pages;

/// <summary>GUID translation explorer (#8).</summary>
public static class GuidExplorer
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · GUID Explorer</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font:14px/1.5 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:800px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
input[type=text]{background:#20242d;border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-size:13px;width:400px}
button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px}
.card h2{font-size:14px;margin-bottom:8px}
.guid-map{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:center;margin:12px 0}
.guid-box{background:#20242d;border:1px solid var(--border);border-radius:6px;padding:10px;font-family:monospace;font-size:12px}
.guid-box .label{color:var(--muted);font-size:10px;text-transform:uppercase;margin-bottom:4px}
.guid-box a{color:var(--accent);text-decoration:none}
.arrow{color:var(--muted);font-size:20px;text-align:center}
.detail{font-size:13px;margin:4px 0}
.detail .lbl{color:var(--muted);display:inline-block;width:100px}
.badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px;font-weight:600;background:#1a3a2a;color:var(--good)}
.empty{color:var(--muted);font-style:italic;padding:20px;text-align:center}
.examples{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.example{background:#20242d;border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;cursor:pointer;color:var(--muted)}
.example:hover{border-color:var(--accent);color:var(--text)}
</style></head><body>
<h1>🔍 GUID Explorer</h1>
<div class="sub">Translate any GUID across IMDB, TMDB, TVDB — paste or type any identifier</div>
<div style="display:flex;gap:8px;align-items:center;margin-bottom:12px">
<input type="text" id="guid" placeholder="e.g. imdb://tt0088763, tmdb://550, tvdb://1234">
<button onclick="lookup()">Translate</button>
</div>
<div class="examples">
  <span class="example" onclick="set('imdb://tt0088763')">imdb://tt0088763</span>
  <span class="example" onclick="set('tmdb://550')">tmdb://550</span>
  <span class="example" onclick="set('tvdb://1234')">tvdb://1234</span>
  <span class="example" onclick="set('tmdb-movie-550')">tmdb-movie-550</span>
  <span class="example" onclick="set('tmdb-show-15260')">tmdb-show-15260</span>
</div>
<div id="result"></div>
<script>
function set(v){document.getElementById('guid').value=v;lookup()}
async function lookup(){
  const guid=document.getElementById('guid').value.trim();if(!guid)return;
  document.getElementById('result').innerHTML='<div class="empty">Looking up…</div>';
  try{
    const r=await fetch('/guid/lookup?guid='+encodeURIComponent(guid));
    if(!r.ok){document.getElementById('result').innerHTML='<div class="empty">Not found: '+guid+'</div>';return}
    const d=await r.json();
    document.getElementById('result').innerHTML=`
      <div class="card"><h2>Translation Results</h2>
        <div class="guid-map">
          <div class="guid-box"><div class="label">Input</div>${guid}</div>
          <div class="arrow">→</div>
          <div class="guid-box"><div class="label">Resolved</div>${d.guid||'—'}</div>
        </div>
        <div class="detail"><span class="lbl">Kind:</span> ${d.kind||'—'} <span class="badge">${d.cached?'cached':'not cached'}</span></div>
        <div class="detail"><span class="lbl">Title:</span> ${d.title||'—'} ${d.year?'('+d.year+')':''}</div>
        <div class="detail"><span class="lbl">TMDB ID:</span> ${d.tmdbId||'—'}</div>
        <div class="detail"><span class="lbl">IMDB:</span> ${d.imdb||'—'} ${d.imdb?'<a href="https://www.imdb.com/title/'+d.imdb+'" target="_blank" style="color:var(--accent)">↗</a>':''}</div>
        <div class="detail"><span class="lbl">TVDB:</span> ${d.tvdb||'—'}</div>
        <div class="detail"><span class="lbl">Item ID:</span> ${d.itemId||'—'}</div>
      </div>`;
  }catch(e){document.getElementById('result').innerHTML='<div class="empty">Error: '+e.message+'</div>'}
}
</script></body></html>
""";
}
