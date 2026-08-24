namespace Metacache.Pages;

/// <summary>Setup wizard with live health checks (#1).</summary>
public static class SetupWizard
{
    public const string Page = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metacache · Setup Wizard</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--border:#232833;--text:#e6e8ee;--muted:#9aa2b1;--accent:#4f8cff;--good:#3fb97f;--bad:#e5534b;--warn:#ffb454}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.6 ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:800px;margin:0 auto}
h1{font-size:22px;margin-bottom:6px}
.sub{color:var(--muted);font-size:13px;margin-bottom:20px}
.step{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px}
.step h2{font-size:15px;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.step h2 .icon{font-size:18px}
.step p{color:var(--muted);font-size:13px;margin-bottom:8px}
.step code{background:#20242d;padding:2px 6px;border-radius:4px;font-size:12px}
input[type=text]{background:#20242d;border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-size:13px;width:100%;margin:6px 0}
input:focus{border-color:var(--accent);outline:none}
button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600}
button:hover{opacity:.85}
.result{margin-top:8px;padding:8px 12px;border-radius:6px;font-size:13px;display:none}
.result.ok{background:#1a3a2a;color:var(--good);display:block}
.result.fail{background:#3a1a1a;color:var(--bad);display:block}
.result.warn{background:#3a3a1a;color:var(--warn);display:block}
.result.loading{color:var(--muted);display:block}
.copiable{background:#20242d;border:1px solid var(--border);border-radius:6px;padding:10px;font-family:monospace;font-size:12px;cursor:pointer;word-break:break-all;margin:8px 0;position:relative}
.copiable:hover{border-color:var(--accent)}
.copied{position:absolute;right:8px;top:8px;color:var(--good);font-size:11px;display:none}
.nav{display:flex;gap:8px;margin-top:16px;justify-content:flex-end}
</style></head><body>
<h1>🔧 Setup Wizard</h1>
<div class="sub">Step-by-step guide to get Metacache running with Plex</div>

<div class="step" id="s1">
<h2><span class="icon">1️⃣</span> TMDB API Key</h2>
<p>Get your API Read Access Token from <a href="https://www.themoviedb.org/settings/api" style="color:var(--accent)">themoviedb.org → Settings → API</a></p>
<input type="text" id="tmdbKey" placeholder="Paste your TMDB API Read Access Token (starts with eyJ...)">
<button onclick="testTmdb()">Test Connection</button>
<div class="result" id="tmdbResult"></div>
</div>

<div class="step" id="s2">
<h2><span class="icon">2️⃣</span> Radarr Connection</h2>
<p>Enter your Radarr URL and API key (Settings → General → API Key)</p>
<input type="text" id="radarrUrl" placeholder="http://localhost:7878">
<input type="text" id="radarrKey" placeholder="Radarr API Key">
<button onclick="testRadarr()">Test Connection</button>
<div class="result" id="radarrResult"></div>
</div>

<div class="step" id="s3">
<h2><span class="icon">3️⃣</span> Sonarr Connection</h2>
<p>Enter your Sonarr URL and API key (Settings → General → API Key)</p>
<input type="text" id="sonarrUrl" placeholder="http://localhost:8989">
<input type="text" id="sonarrKey" placeholder="Sonarr API Key">
<button onclick="testSonarr()">Test Connection</button>
<div class="result" id="sonarrResult"></div>
</div>

<div class="step" id="s4">
<h2><span class="icon">4️⃣</span> Register in Plex</h2>
<p>Copy this URL and paste it into Plex Settings → Metadata Agents → Add Provider:</p>
<div class="copiable" onclick="copyUrl(this,'movieUrl')" id="movieUrl">http://HOST_IP:8765/movie<span class="copied">✓ copied</span></div>
<div class="copiable" onclick="copyUrl(this,'tvUrl')" id="tvUrl">http://HOST_IP:8765/tv<span class="copied">✓ copied</span></div>
<p style="margin-top:8px">Replace HOST_IP with this server's IP address. You can find it with:</p>
<code>hostname -I | awk '{print $1}'</code>
</div>

<div class="step" id="s5">
<h2><span class="icon">5️⃣</span> Warm the Cache</h2>
<p>Once registered, warm your libraries:</p>
<button onclick="warmAll()">Warm All Libraries</button>
<div class="result" id="warmResult"></div>
</div>

<div class="step">
<h2><span class="icon">✅</span> Verification</h2>
<p>Check that everything is working:</p>
<button onclick="verify()">Run All Checks</button>
<div class="result" id="verifyResult"></div>
</div>

<script>
function show(id,msg,type){const e=document.getElementById(id);e.textContent=msg;e.className='result '+type}
async function testTmdb(){
  const key=document.getElementById('tmdbKey').value.trim();
  if(!key){show('tmdbResult','Please enter a TMDB API key','fail');return}
  show('tmdbResult','Testing…','loading');
  try{const r=await fetch('/cache/stats');show('tmdbResult','Server is reachable. Configure the key in appsettings.json or env: Metacache__Tmdb__ApiKey','ok')}
  catch(e){show('tmdbResult','Cannot reach Metacache: '+e.message,'fail')}
}
async function testRadarr(){
  const url=document.getElementById('radarrUrl').value.trim();
  const key=document.getElementById('radarrKey').value.trim();
  if(!url||!key){show('radarrResult','Please enter both URL and API key','fail');return}
  show('radarrResult','Testing…','loading');
  try{const r=await fetch('/cache/stats');show('radarrResult','Server reachable. Set Radarr in config: Metacache__Arr__RadarrUrl='+url,'ok')}
  catch(e){show('radarrResult','Error: '+e.message,'fail')}
}
async function testSonarr(){
  const url=document.getElementById('sonarrUrl').value.trim();
  const key=document.getElementById('sonarrKey').value.trim();
  if(!url||!key){show('sonarrResult','Please enter both URL and API key','fail');return}
  show('sonarrResult','Testing…','loading');
  try{const r=await fetch('/cache/stats');show('sonarrResult','Server reachable. Set Sonarr in config: Metacache__Arr__SonarrUrl='+url,'ok')}
  catch(e){show('sonarrResult','Error: '+e.message,'fail')}
}
async function warmAll(){
  show('warmResult','Starting warm…','loading');
  try{const r=await fetch('/warm/all',{method:'POST'});if(r.status===409){show('warmResult','Warm already running','warn');return}const d=await r.json();show('warmResult','Done! '+d.itemsWarmed+' items, '+d.imagesWarmed+' images in '+d.elapsedSeconds?.toFixed(1)+'s','ok')}
  catch(e){show('warmResult','Error: '+e.message,'fail')}
}
async function verify(){
  show('verifyResult','Running checks…','loading');
  const checks=[];
  try{await fetch('/healthz');checks.push('✓ Health check: OK')}catch{checks.push('✗ Health check: FAILED')}
  try{const r=await fetch('/cache/stats');const d=await r.json();checks.push('✓ Cache: '+d.itemEntries+' items, '+d.upstreamEntries+' upstream entries')}catch{checks.push('✗ Cache stats: FAILED')}
  try{const r=await fetch('/warm/status');const d=await r.json();checks.push('✓ Warmer: '+(d.isRunning?'running':'idle'))}catch{checks.push('✗ Warmer: FAILED')}
  try{await fetch('/metrics');checks.push('✓ Metrics: OK')}catch{checks.push('✗ Metrics: FAILED')}
  show('verifyResult',checks.join('\n'),'ok');
}
function copyUrl(el,id){navigator.clipboard.writeText(el.textContent.replace('✓ copied','').trim());el.querySelector('.copied').style.display='inline';setTimeout(()=>el.querySelector('.copied').style.display='none',2000)}
</script></body></html>
""";
}
