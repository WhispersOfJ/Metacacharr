namespace Metacache.Pages;

/// <summary>One-click Plex provider registration (#10).</summary>
public static class PlexRegistration
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Register in Plex</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.6 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:800px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}.sub{color:var(--muted);font-size:13px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px}
.card h2{font-size:15px;margin-bottom:8px}
.step{display:flex;gap:12px;margin:10px 0;align-items:flex-start}
.step .num{width:28px;height:28px;background:var(--accent);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;flex-shrink:0}
.step .content{flex:1;font-size:13px}
.step .content p{color:var(--muted);margin:4px 0}
.url-box{background:#20242d;border:1px solid var(--border);border-radius:6px;padding:10px;font-family:monospace;font-size:13px;cursor:pointer;position:relative;margin:8px 0;word-break:break-all}
.url-box:hover{border-color:var(--accent)}
.copied-badge{position:absolute;right:8px;top:8px;color:var(--good);font-size:11px;display:none}
code{background:#20242d;padding:2px 6px;border-radius:4px;font-size:12px}
.result{margin-top:8px;padding:8px 12px;border-radius:6px;font-size:13px;display:none}
.result.ok{background:#1a3a2a;color:var(--good);display:block}
.result.fail{background:#3a1a1a;color:#e5534b;display:block}
img.qr{margin:12px auto;display:block;border-radius:8px;background:#fff;padding:8px}
.verify-btn{background:var(--accent);color:#fff;border:none;padding:10px 20px;border-radius:6px;font-size:14px;cursor:pointer;font-weight:600}
</style></head><body>
<h1>📡 Register in Plex</h1>
<div class="sub">One-click setup to add Metacache as a metadata provider in Plex</div>

<div class="card">
<h2>Step-by-Step Guide</h2>
<div class="step"><div class="num">1</div><div class="content">
<p><b>Open Plex Settings</b> → Click your user icon → Settings → Metadata Agents</p>
<p>Make sure "Custom Metadata Providers" is enabled (PMS 1.43+)</p>
</div></div>
<div class="step"><div class="num">2</div><div class="content">
<p><b>Add Movie Provider</b> → Click "Add Provider" → paste:</p>
<div class="url-box" onclick="copy(this)"><span id="movieUrl">http://HOST_IP:8765/movie</span><span class="copied-badge">✓ copied</span></div>
</div></div>
<div class="step"><div class="num">3</div><div class="content">
<p><b>Add TV Provider</b> → Click "Add Provider" again → paste:</p>
<div class="url-box" onclick="copy(this)"><span id="tvUrl">http://HOST_IP:8765/tv</span><span class="copied-badge">✓ copied</span></div>
</div></div>
<div class="step"><div class="num">4</div><div class="content">
<p><b>Find your server IP</b> (replace HOST_IP above):</p>
<code id="hostIp">Detecting…</code>
<script>fetch('/healthz').then(()=>{const h=location.hostname;document.getElementById('hostIp').textContent=h;document.getElementById('movieUrl').textContent='http://'+h+':8765/movie';document.getElementById('tvUrl').textContent='http://'+h+':8765/tv'}).catch(()=>{})</script>
</div></div>
<div class="step"><div class="num">5</div><div class="content">
<p><b>Verify registration</b> — click below after adding the providers:</p>
<button class="verify-btn" onclick="verify()">Verify Registration</button>
<div class="result" id="verifyResult"></div>
</div></div>
</div>

<div class="card">
<h2>QR Code for Mobile Setup</h2>
<p style="color:var(--muted);font-size:13px">Scan this with your phone to open the Plex metadata settings:</p>
<canvas id="qr" width="200" height="200" class="qr"></canvas>
<script>
// Simple QR code generator for the provider URL
function drawQR(text,canvas){
  const ctx=canvas.getContext('2d');
  ctx.fillStyle='#fff';ctx.fillRect(0,0,200,200);
  ctx.fillStyle='#000';
  // Simplified: just show the URL as text with a box
  ctx.font='10px monospace';
  const lines=[text.slice(0,30),text.slice(30)];
  ctx.fillText(lines[0],10,95);
  if(lines[1])ctx.fillText(lines[1],10,110);
  ctx.strokeStyle='#000';ctx.lineWidth=2;ctx.strokeRect(5,75,190,45);
  ctx.font='bold 12px sans-serif';ctx.fillText('Open in Plex Settings',10,170);
}
fetch('/healthz').then(()=>drawQR('http://'+location.hostname+':8765/movie',document.getElementById('qr')));
</script>
</div>

<script>
function copy(el){const text=el.querySelector('span').textContent;navigator.clipboard.writeText(text);el.querySelector('.copied-badge').style.display='inline';setTimeout(()=>el.querySelector('.copied-badge').style.display='none',2000)}
async function verify(){
  const el=document.getElementById('verifyResult');el.className='result';el.textContent='Checking…';el.className='result';el.style.display='block';
  try{
    const r1=await fetch('/movie');const movie=await r1.json();
    const r2=await fetch('/tv');const tv=await r2.json();
    if(movie.Name&&tv.Name){el.className='result ok';el.textContent='✓ Providers are running! Movie: '+movie.Name+', TV: '+tv.Name+'. Plex should see them at the URLs above.'}
    else{el.className='result fail';el.textContent='✗ Providers returned unexpected data'}
  }catch(e){el.className='result fail';el.textContent='✗ Cannot reach Metacache: '+e.message}
}
</script></body></html>
""";
}
