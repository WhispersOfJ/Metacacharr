namespace Metacache.Pages;

/// <summary>Cache freshness heatmap (#4).</summary>
public static class CacheFreshness
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Cache Freshness</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f;--bad:#e5534b;--warn:#ffb454}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.6 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:1100px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center}
.stat .num{font-size:28px;font-weight:700}.stat .lbl{color:var(--muted);font-size:11px;text-transform:uppercase}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px}
.card h2{font-size:14px;margin-bottom:8px}
.bar-row{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:13px}
.bar-row .name{width:70px;color:var(--muted);text-transform:capitalize}
.bar-track{flex:1;height:18px;background:#20242d;border-radius:4px;overflow:hidden;display:flex}
.bar-seg{height:100%;transition:width .3s}
.seg-fresh{background:var(--good)}.seg-stale{background:var(--warn)}.seg-expired{background:var(--bad)}
.legend{display:flex;gap:12px;font-size:11px;color:var(--muted);margin-top:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:3px;vertical-align:-1px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;color:var(--muted);font-weight:500;padding:5px 6px;border-bottom:1px solid var(--border);font-size:11px;text-transform:uppercase}
td{padding:4px 6px;border-bottom:1px solid #1c2029}
.badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600}
.badge.f{background:#1a3a2a;color:var(--good)}.badge.s{background:#3a3a1a;color:var(--warn)}.badge.e{background:#3a1a1a;color:var(--bad)}
</style></head><body>
<h1>📊 Cache Freshness</h1>
<div class="sub">Visual overview of what's fresh, stale, and expired — polls /admin/items every 5s</div>
<div class="grid" id="stats"></div>
<div class="card">
<h2>By Kind</h2>
<div id="kinds"></div>
<div class="legend"><i class="seg-fresh"></i>Fresh<i class="seg-stale"></i>Stale<i class="seg-expired"></i>Expired</div>
</div>
<div class="card">
<h2>Expiring Soon (next 24h)</h2>
<div style="max-height:300px;overflow-y:auto">
<table><thead><tr><th>Title</th><th>Kind</th><th>Lang</th><th>Status</th><th>Expires</th></tr></thead>
<tbody id="expiring"></tbody></table>
</div>
</div>
<script>
function fmt(d){if(!d)return'—';return new Date(d).toLocaleString()}
async function poll(){
  try{
    const now=new Date();
    const [movieR,showR,seasonR,epR]=await Promise.all([
      fetch('/admin/items?kind=movie&limit=500'),fetch('/admin/items?kind=show&limit=500'),
      fetch('/admin/items?kind=season&limit=500'),fetch('/admin/items?kind=episode&limit=500')
    ]);
    const kinds={};
    for(const[name,r]of [['movie',movieR],['show',showR],['season',seasonR],['episode',epR]]){
      const d=await r.json();const items=d.items||[];
      let fresh=0,stale=0,expired=0;
      for(const i of items){
        const exp=i.expiresAt?new Date(i.expiresAt):null;
        if(!exp||exp>now)fresh++;else if(exp>new Date(now-12*3600*1000))stale++;else expired++;
      }
      kinds[name]={total:items.length,fresh,stale,expired};
    }
    const total=Object.values(kinds).reduce((a,k)=>a+k.total,0);
    const totalFresh=Object.values(kinds).reduce((a,k)=>a+k.fresh,0);
    const totalStale=Object.values(kinds).reduce((a,k)=>a+k.stale,0);
    const totalExpired=Object.values(kinds).reduce((a,k)=>a+k.expired,0);
    document.getElementById('stats').innerHTML=`
      <div class="stat"><div class="num" style="color:var(--text)">${total}</div><div class="lbl">Total Items</div></div>
      <div class="stat"><div class="num" style="color:var(--good)">${totalFresh}</div><div class="lbl">Fresh</div></div>
      <div class="stat"><div class="num" style="color:var(--warn)">${totalStale}</div><div class="lbl">Stale</div></div>
      <div class="stat"><div class="num" style="color:var(--bad)">${totalExpired}</div><div class="lbl">Expired</div></div>`;
    const kindsEl=document.getElementById('kinds');kindsEl.innerHTML='';
    for(const[kind,d]of Object.entries(kinds)){
      const pct=d.total?100:0;
      const fp=d.total?d.fresh/d.total*100:0;
      const sp=d.total?d.stale/d.total*100:0;
      const ep=d.total?d.expired/d.total*100:0;
      kindsEl.innerHTML+=`<div class="bar-row"><span class="name">${kind}</span><div class="bar-track"><div class="bar-seg seg-fresh" style="width:${fp}%"></div><div class="bar-seg seg-stale" style="width:${sp}%"></div><div class="bar-seg seg-expired" style="width:${ep}%"></div></div><span>${d.total}</span></div>`;
    }
    // Expiring soon — fetch all and find items expiring within 24h
    const allR=await fetch('/admin/items?limit=500');
    const allD=await allR.json();
    const expiring=(allD.items||[]).filter(i=>{const e=i.expiresAt?new Date(i.expiresAt):null;return e&&e>now&&e<new Date(now+86400000)}).sort((a,b)=>new Date(a.expiresAt)-new Date(b.expiresAt)).slice(0,50);
    const tbody=document.getElementById('expiring');
    tbody.innerHTML=expiring.length?expiring.map(i=>`<tr><td>${i.title||'—'}</td><td>${i.kind}</td><td>${i.lang}</td><td><span class="badge ${i.fresh?'f':'s'}">${i.fresh?'fresh':'stale'}</span></td><td>${fmt(i.expiresAt)}</td></tr>`).join(''):'<tr><td colspan="5" class="empty" style="padding:20px">No items expiring in the next 24h</td></tr>';
  }catch(e){}
}
setInterval(poll,5000);poll();
</script></body></html>
""";
}
