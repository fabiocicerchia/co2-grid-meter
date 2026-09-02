"""The pages the device serves itself, apart from the server that serves them.

Markup and CSS are not routing: `http.py` is a socket loop and a request
parser, and mixing a 90-line stylesheet into it is what made that file hard to
read. Nothing here imports anything from the firmware.

Imported by bare module name, like every other module under pico/ — see
CLAUDE.md.
"""

MINI_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>CO₂ Pico</title></head>
<body><h3>Pico local pages</h3><ul><li><a href='/html/graph'>Graph</a></li><li><a href='/system-info'>System info JSON</a></li></ul></body></html>"""

GRAPH_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>CO₂ graph</title></head>
<body><h3>Last 48h CO₂ (gCO₂/kWh)</h3><canvas id='c' width='640' height='280' style='border:1px solid #ccc'></canvas>
<script>
fetch('/em/window?back_hours=48').then(r=>r.json()).then(j=>{
 const h=(j.history||[]).map(x=>Number(x.carbonIntensity)).filter(Number.isFinite);
 const c=document.getElementById('c'),ctx=c.getContext('2d'); if(!h.length){ctx.fillText('No data',10,20);return;}
 const mn=Math.min(...h),mx=Math.max(...h),w=c.width,hg=c.height,pad=20;
 ctx.beginPath(); h.forEach((v,i)=>{const x=pad+i*(w-2*pad)/Math.max(1,h.length-1);const y=hg-pad-((v-mn)/(Math.max(1,mx-mn)))*(hg-2*pad); i?ctx.lineTo(x,y):ctx.moveTo(x,y)}); ctx.stroke();
});
</script></body></html>"""


def build_index_html():
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pico CO₂ Status</title>
  <style>
    :root { color-scheme: light dark; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f3f4f6; color: #111827; }
    .page { max-width: 740px; margin: 0 auto; padding: 18px; }
    .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.08); padding: 14px; margin-bottom: 12px; }
    h1 { margin: 0 0 8px 0; font-size: 22px; }
    .muted { color: #6b7280; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 12px; }
    .k { font-size: 12px; color: #6b7280; }
    .v { font-weight: 600; margin-top: 2px; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 8px; }
    button { border: none; border-radius: 8px; padding: 8px 12px; background: #2563eb; color: #fff; cursor: pointer; font-weight: 600; }
    .themeBtn { background: #4b5563; }
    .pill { display: inline-block; border-radius: 999px; background: #e5e7eb; padding: 2px 8px; font-size: 12px; font-weight: 600; color: #111827; }
    .ok { background: #d1fae5; color: #065f46; }
    .wait { background: #fef3c7; color: #92400e; }
    .no { background: #fee2e2; color: #991b1b; }
    body.dark { background: #111827; color: #f9fafb; }
    body.dark .card { background: #1f2937; border-color: #374151; }
    body.dark .muted, body.dark .k { color: #9ca3af; }
    body.dark .pill { background: #374151; color: #f9fafb; }
    @media (prefers-color-scheme: dark) {
      body.auto { background: #111827; color: #f9fafb; }
      body.auto .card { background: #1f2937; border-color: #374151; }
      body.auto .muted, body.auto .k { color: #9ca3af; }
      body.auto .pill { background: #374151; color: #f9fafb; }
    }
  </style>
</head>
<body class="auto">
  <main class="page">
    <section class="card">
      <h1><span id="city">--</span> grid CO₂ status</h1>
      <div class="muted" id="meta">Waiting for /status...</div>
      <div class="row">
        <button id="refresh">Refresh</button>
        <button id="theme" class="themeBtn">Dark mode</button>
        <span class="muted">Auto refresh every 30s</span>
      </div>
    </section>
    <section class="card">
      <div class="grid">
        <div><div class="k">Carbon intensity</div><div class="v"><span id="ci">--</span> gCO₂/kWh</div></div>
        <div><div class="k">Provider</div><div class="v" id="provider">--</div></div>
        <div><div class="k">Recommendation</div><div class="v"><span class="pill" id="verdict">--</span></div></div>
        <div><div class="k">Reason</div><div class="v" id="reason">--</div></div>
        <div><div class="k">Wait hours</div><div class="v" id="wait">--</div></div>
        <div><div class="k">Next best</div><div class="v" id="next">--</div></div>
      </div>
    </section>
  </main>
  <script>
    const els = { city:city, meta:meta, ci:ci, provider:provider, verdict:verdict, reason:reason, wait:wait, next:next, refresh:refresh, theme:theme };
    function verdictClass(v){ if(v==='GO')return 'pill ok'; if(v==='WAIT')return 'pill no'; return 'pill wait'; }
    function fill(data){ const rec=data.recommendation||{}; els.city.textContent=data.city||'--'; els.meta.textContent=`${data.cc||'--'} • ${data.datetime||'--'} • lat ${data.lat ?? '--'}, lon ${data.lon ?? '--'}`; els.ci.textContent=data.carbonIntensity ?? '--'; els.provider.textContent=data._provider||'--'; els.verdict.textContent=rec.verdict||'--'; els.verdict.className=verdictClass(rec.verdict||''); els.reason.textContent=rec.reason||'--'; els.wait.textContent=rec.wait_hours ?? '--'; els.next.textContent=rec.next_best||'--'; }
    function applyTheme(mode){
      document.body.className = mode;
      els.theme.textContent = mode === 'dark' ? 'Light mode' : 'Dark mode';
      try { localStorage.setItem('pico_theme', mode); } catch (_) {}
    }
    function initTheme(){
      let mode = 'auto';
      try { mode = localStorage.getItem('pico_theme') || 'auto'; } catch (_) {}
      if (mode !== 'dark' && mode !== 'auto') mode = 'auto';
      applyTheme(mode);
    }
    async function load(){ try{ const res=await fetch('/status',{cache:'no-store'}); if(!res.ok)throw new Error('HTTP '+res.status); fill(await res.json()); }catch(err){ els.meta.textContent='Error loading /status: '+err.message; } }
    els.refresh.addEventListener('click', load);
    els.theme.addEventListener('click', ()=>applyTheme(document.body.className === 'dark' ? 'auto' : 'dark'));
    initTheme();
    load();
    setInterval(load, 30000);
  </script>
</body>
</html>
"""
