namespace Metacache.Pages;

/// <summary>Provider health dashboard (#7).</summary>
public static class ProviderHealth
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Provider Health</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f;--bad:#e5534b;--warn:#ffb454}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.6 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:1100px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}
.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}
.card .title{font-size:14px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.dot.ok{background:var(--good)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}.dot.unknown{background:var(--muted)}
.metric{display:flex;justify-content:space-between;margin:4px 0;font-size:13px}
.metric .label{color:var(--muted)}
canvas{width:100%;height:60px;display:block;margin-top:6px}
.empty{color:var(--muted);font-style:italic;font-size:13px;padding:20px;text-align:center}
</style></head><body>
<h1>🏥 Provider Health</h1>
<div class="sub">Real-time status of all upstream providers — polls /metrics every 3s</div>
<div class="grid" id="providers"></div>
<script>
const providerMeta={
  'tmdb':{name:'TMDB API',icon:'🎬',desc:'Movie + show metadata'},
  'api4.thetvdb.com':{name:'TVDB v4',icon:'📺',desc:'Episode fallback'},
  'images':{name:'TMDB Images',icon:'🖼️',desc:'Artwork cache'},
  'webservice.fanart.tv':{name:'Fanart',icon:'🎨',desc:'Show artwork'},
  'radarr':{name:'Radarr',icon:'📦',desc:'Movie library'},
  'sonarr':{name:'Sonarr',icon:'📦',desc:'Show library'}
};
const sparkData={};
function humanize(b){if(b==null)return'—';if(b<1024)return b+' B';const u=['KB','MB','GB','TB'];let i=-1;do{b/=1024;i++}while(b>=1024&&i<u.length-1);return b.toFixed(1)+' '+u[i]}
async function poll(){
  try{
    const r=await fetch('/metrics');if(!r.ok)throw new Error('HTTP '+r.status);
    const m=await r.json();
    const el=document.getElementById('providers');
    const providers=m.perProviderDuration||{};
    const entries=Object.entries(providers);
    if(!entries.length){el.innerHTML='<div class="empty">No provider data yet — warm your libraries first</div>';return}
    el.innerHTML='';
    for(const[name,data]of entries){
      const meta=providerMeta[name]||{name,icon:'📡',desc:''};
      const p50=data.p50||0,p95=data.p95||0;
      const ok=p50<2&&p95<5;
      if(!sparkData[name])sparkData[name]=[];
      sparkData[name].push(p50);if(sparkData[name].length>60)sparkData[name].shift();
      const card=document.createElement('div');card.className='card';
      card.innerHTML=`<div class="title"><span class="dot ${ok?'ok':p50<5?'warn':'bad'}"></span>${meta.icon} ${meta.name}<span style="color:var(--muted);font-weight:400;font-size:12px;margin-left:auto">${meta.desc}</span></div>
        <div class="metric"><span class="label">Latency p50</span><span>${p50.toFixed(0)}ms</span></div>
        <div class="metric"><span class="label">Latency p95</span><span>${p95.toFixed(0)}ms</span></div>
        <canvas id="spark-${name}"></canvas>`;
      el.appendChild(card);
      drawSpark('spark-'+name,sparkData[name]);
    }
  }catch(e){}
}
function drawSpark(id,data){
  const c=document.getElementById(id);if(!c||!data.length)return;
  const dpr=devicePixelRatio||1;const w=c.clientWidth,h=c.clientHeight;
  c.width=w*dpr;c.height=h*dpr;const ctx=c.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);
  const max=Math.max(...data,1);ctx.strokeStyle='#4f8cff';ctx.lineWidth=1.5;ctx.beginPath();
  for(let i=0;i<data.length;i++){const x=i/(Math.max(data.length-1,1))*w,y=h-data[i]/max*h;i?ctx.lineTo(x,y):ctx.moveTo(x,y)}
  ctx.stroke();
}
setInterval(poll,3000);poll();
</script></body></html>
""";
}
