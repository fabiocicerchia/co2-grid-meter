/* ----------------- config + helpers ----------------- */
const K = {
  PICO: "co2_meter_pico_url_v1",
  THEME: "co2_meter_theme_v1",
  AUTO: "co2_meter_auto_refresh_v1",
  INT: "co2_meter_auto_interval_v1",
  GLAT: "geo_lat", GLON: "geo_lon", GCITY: "geo_city", GCC: "geo_cc",
};
const CFG = { BACK_H: 48, FWD_H: 12, LEDS: 12, GREEN: 4, YELLOW: 4, P_GREEN: 0.33, P_YELLOW: 0.66 };

const $ = (id) => document.getElementById(id);
const setText = (id, v) => { const el = $(id); if (el) el.textContent = v; };
const cssVar = (n) => getComputedStyle(document.body).getPropertyValue(n).trim();
const ls = { get: (k, d = "") => localStorage.getItem(k) ?? d, set: (k, v) => localStorage.setItem(k, v) };
const num = (v, d = 0) => (Number.isFinite(+v) ? +v : d);
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

const I18N = {
  en: {
    dashboard_title_suffix: 'grid CO₂ dashboard (local)', auto_refresh: 'Auto refresh', refresh_now: 'Refresh now',
    current: 'Current', intensity: 'Intensity', recommendation: 'Recommendation', reason: 'Reason',
    next_window: 'Next window', chart_title: 'Past 48h + Next 12h'
  },
  it: {
    dashboard_title_suffix: 'dashboard CO₂ di rete (locale)', auto_refresh: 'Aggiornamento automatico', refresh_now: 'Aggiorna ora',
    current: 'Attuale', intensity: 'Intensità', recommendation: 'Raccomandazione', reason: 'Motivo',
    next_window: 'Prossima finestra', chart_title: 'Ultime 48h + Prossime 12h'
  }
};

function applyI18n(lang) {
  const dict = I18N[lang] || I18N.en;
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) el.textContent = dict[key];
  });
}

const loadPico = () => ls.get(K.PICO, "");
const savePico = (v) => ls.set(K.PICO, v);
const getTheme = () => ls.get(K.THEME, "");
const setTheme = (m) => ls.set(K.THEME, m);
const getAuto = () => ls.get(K.AUTO, "0") === "1";
const setAuto = (v) => ls.set(K.AUTO, v ? "1" : "0");
const getInterval = () => num(ls.get(K.INT, "30000"), 30000);
const setIntervalStore = (ms) => ls.set(K.INT, String(ms));

const extractSeries = (j) =>
  (Array.isArray(j?.history) ? j.history : Array.isArray(j?.data) ? j.data : Array.isArray(j) ? j : [])
    .map((p) => ({ t_ms: Date.parse(p.datetime), ci: +p.carbonIntensity }))
    .filter((p) => Number.isFinite(p.t_ms) && Number.isFinite(p.ci))
    .sort((a, b) => a.t_ms - b.t_ms);

/* ----------------- location override (from localStorage) ----------------- */
function geoQS(prefix = "&") {
  const lat = ls.get(K.GLAT, "").trim();
  const lon = ls.get(K.GLON, "").trim();
  const cc = ls.get(K.GCC, "").trim();
  const city = ls.get(K.GCITY, "").trim();

  const q = new URLSearchParams();
  if (lat && lon) { q.set("lat", lat); q.set("lon", lon); }
  if (cc) q.set("cc", cc);
  if (city) q.set("city", city);

  const s = q.toString();
  return s ? (prefix + s) : "";
}

/* ----------------- LED meter ----------------- */
const percentile = (sorted, x) => {
  const n = sorted.length; if (!n) return null;
  let lo = 0, hi = n;
  while (lo < hi) { const m = (lo + hi) >> 1; (sorted[m] < x) ? (lo = m + 1) : (hi = m); }
  return lo / n;
};

function initLedMeter() {
  const meter = $("meter"); if (!meter) return;
  meter.innerHTML = "";
  for (let i = 0; i < CFG.LEDS; i++) {
    const d = document.createElement("div");
    d.className = "led";
    d.dataset.color = i < CFG.GREEN ? "green" : i < CFG.GREEN + CFG.YELLOW ? "yellow" : "red";
    meter.appendChild(d);
  }
}

function setLedMeter(level, label = "—") {
  const meter = $("meter"); if (!meter) return;
  meter.querySelectorAll(".led").forEach((el, i) => {
    const on = i < level, c = el.dataset.color;
    el.className = "led" + (on ? ` on ${c}` : "");
  });
  setText("meterLabel", label);
}

function meterFromWeekDistribution(currentCi, weekSeries) {
  const vals = (weekSeries || []).map((p) => p.ci).filter(Number.isFinite).sort((a, b) => a - b);
  if (vals.length < 12) return setLedMeter(0, "Collecting baseline…");
  const p = percentile(vals, currentCi); if (p == null) return setLedMeter(0, "No baseline");

  const level = clamp(Math.round(p * CFG.LEDS), 0, CFG.LEDS);
  const zone = p <= CFG.P_GREEN ? "cleaner than usual" : p <= CFG.P_YELLOW ? "around average" : "dirtier than usual";
  setLedMeter(level, `${zone} • p${Math.round(p * 100)}`);
}

/* ----------------- chart ----------------- */
const DOW = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

function sizeCanvasToContainer(c) {
  const p = c?.parentElement; if (!p) return;
  const r = p.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  c.width = Math.max(200, Math.floor(r.width * dpr));
  c.height = Math.max(200, Math.floor(r.height * dpr));
}

function drawChart(cur, overlayShifted) {
  const canvas = $("chart"); if (!canvas) return;
  sizeCanvasToContainer(canvas);

  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.width, H = canvas.height;
  const w = W / dpr, h = H / dpr;

  const C = {
    axis: cssVar("--axis") || "#bbb",
    grid: cssVar("--grid") || "#eee",
    line: cssVar("--line") || "#111",
    overlay: cssVar("--overlay") || "#666",
    now: cssVar("--now") || "#999",
    midnight: cssVar("--midnight") || "#c7c7c7",
    fg: cssVar("--fg") || "#111",
  };

  ctx.clearRect(0, 0, W, H);
  ctx.save();
  ctx.scale(1 / dpr, 1 / dpr);

  const pad = { L: 64, R: 20, T: 18, B: 88 };
  const x0 = pad.L, y0 = pad.T, x1 = w - pad.R, y1 = h - pad.B;

  ctx.strokeStyle = C.axis;
  ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);

  const now = Date.now();
  const start = now - CFG.BACK_H * 3600e3;
  const end = now + CFG.FWD_H * 3600e3;

  const curClip = (cur || []).filter((p) => p.t_ms >= start && p.t_ms <= now);
  const ovClip = (overlayShifted || []).filter((p) => p.t_ms >= start && p.t_ms <= end);
  const all = curClip.concat(ovClip);

  if (all.length < 2) {
    ctx.fillStyle = C.fg; ctx.font = "14px system-ui";
    ctx.fillText("No data yet (or endpoint not available).", x0 + 10, y0 + 24);
    ctx.restore(); return;
  }

  let min = Infinity, max = -Infinity;
  for (const p of all) { min = Math.min(min, p.ci); max = Math.max(max, p.ci); }
  if (max === min) max = min + 1;

  const X = (t) => x0 + ((t - start) * (x1 - x0)) / Math.max(1, end - start);
  const Y = (ci) => y1 - ((ci - min) * (y1 - y0)) / (max - min);

  ctx.fillStyle = C.fg; ctx.font = "12px system-ui";
  ctx.fillText(String(Math.round(max)), 10, y0 + 12);
  ctx.fillText(String(Math.round(min)), 10, y1);

  const hourMs = 3600e3;
  const firstHour = Math.floor(start / hourMs) * hourMs;
  const midnights = [];

  ctx.font = "11px system-ui";
  for (let t = firstHour; t <= end; t += hourMs) {
    const x = X(t), d = new Date(t), isMidnight = d.getHours() === 0;

    ctx.strokeStyle = isMidnight ? C.midnight : C.grid;
    ctx.lineWidth = isMidnight ? 2 : 1;
    ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y1); ctx.stroke();
    ctx.lineWidth = 1;

    ctx.strokeStyle = C.axis;
    ctx.beginPath(); ctx.moveTo(x, y1); ctx.lineTo(x, y1 + (isMidnight ? 10 : 6)); ctx.stroke();

    const hr = d.getHours();
    if (!isMidnight && hr % 2 === 0) {
      ctx.save();
      ctx.translate(x, y1 + 22);
      ctx.rotate(-Math.PI / 4);
      ctx.fillStyle = C.fg;
      ctx.fillText(String(hr).padStart(2, "0") + ":00", 0, 0);
      ctx.restore();
    }
    if (isMidnight) midnights.push({ x, d });
  }

  for (const m of midnights) {
    const d = m.d, dd = String(d.getDate()).padStart(2, "0"), mm = String(d.getMonth() + 1).padStart(2, "0");
    ctx.fillStyle = C.fg;
    ctx.font = "bold 12px system-ui";
    ctx.fillText(DOW[d.getDay()], m.x - 14, y1 + 40);
    ctx.font = "12px system-ui";
    ctx.fillText(`${dd}/${mm}`, m.x - 18, y1 + 56);
  }

  const poly = (series, dotted) => {
    if (!series || series.length < 2) return;
    const s = series.slice().sort((a, b) => a.t_ms - b.t_ms);
    ctx.beginPath();
    ctx.lineWidth = 2;
    ctx.setLineDash(dotted ? [6, 6] : []);
    ctx.strokeStyle = dotted ? C.overlay : C.line;
    ctx.moveTo(X(s[0].t_ms), Y(s[0].ci));
    for (let i = 1; i < s.length; i++) ctx.lineTo(X(s[i].t_ms), Y(s[i].ci));
    ctx.stroke();
    ctx.setLineDash([]);
  };

  poly(curClip, false);
  poly(ovClip, true);

  ctx.strokeStyle = C.now;
  ctx.setLineDash([3, 3]);
  ctx.beginPath(); ctx.moveTo(X(now), y0); ctx.lineTo(X(now), y1); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = C.fg; ctx.font = "12px system-ui";
  ctx.fillText("now", X(now) + 6, y0 + 14);

  ctx.fillStyle = C.fg; ctx.font = "12px system-ui";
  ctx.fillText("Actual (past 48h)", x0 + 10, y0 + 14);
  ctx.setLineDash([6, 6]);
  ctx.strokeStyle = C.overlay;
  ctx.beginPath(); ctx.moveTo(x0 + 150, y0 + 10); ctx.lineTo(x0 + 195, y0 + 10); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillText("Past-week overlay (incl. next 12h)", x0 + 205, y0 + 14);

  ctx.restore();
}

/* ----------------- data fetch ----------------- */
let lastOverlayShifted = [];
let lastCurrentCi = null;

async function loadWindowFromServer() {
  const pico = ($("pico")?.value || "").trim();
  const qs = pico ? `&pico=${encodeURIComponent(pico)}` : "";
  const r1 = await fetch(`/api/em/window?back_hours=${CFG.BACK_H}${geoQS("&")}${qs}`, { cache: "no-store" });
  const j1 = await r1.json();
  if (j1?.error) throw new Error(j1.error);

  const r2 = await fetch(`/api/em/window-overlay?back_hours=${CFG.BACK_H}&forward_hours=${CFG.FWD_H}${geoQS("&")}${qs}`, { cache: "no-store" });
  const j2 = await r2.json();
  if (j2?.error) throw new Error(j2.error);

  setText("city", j1.city ?? j1?._resolved?.city ?? "—");
  setText("provider", j1._provider ?? "—");

  const cur = extractSeries(j1);
  const prev = extractSeries(j2);
  lastOverlayShifted = prev.map((p) => ({ t_ms: p.t_ms + 7 * 24 * 3600e3, ci: p.ci }));

  drawChart(cur, lastOverlayShifted);
  if (Number.isFinite(lastCurrentCi)) meterFromWeekDistribution(lastCurrentCi, lastOverlayShifted);
}

async function pollPicoStatus() {
  const pico = ($("pico")?.value || "").trim();
  const qs = pico ? `?pico=${encodeURIComponent(pico)}` : "";
  const j = await fetch(`/api/status${qs}`, { cache: "no-store" }).then((r) => r.json());

  if (j?.error) {
    ["ci","verdict","next","device"].forEach((id) => setText(id, "—"));
    setText("reason", j.error);
    lastCurrentCi = null;
    return setLedMeter(0, "No current data");
  }

  const ci = Number(j.carbonIntensity ?? j.carbon_intensity ?? j.co2);
  lastCurrentCi = ci;

  setText("ci", Number.isFinite(ci) ? Math.round(ci) : "—");
  setText("verdict", j.recommendation?.verdict ?? "—");
  setText("reason", j.recommendation?.reason ?? "—");
  setText("next", j.recommendation?.next_best ?? j.recommendation?.next_good_window ?? "—");

  if (Number.isFinite(ci)) meterFromWeekDistribution(ci, lastOverlayShifted);
}

async function refreshAllOnce() {
  await Promise.allSettled([pollPicoStatus(), loadWindowFromServer()]);
  resetProgress();
}

/* ----------------- theme ----------------- */
function applyTheme(mode) {
  const dark = mode === "dark";
  document.body.classList.toggle("dark", dark);
  if ($("themeToggle")) $("themeToggle").checked = dark;
  setText("themeText", dark ? "Dark" : "Light");
  loadWindowFromServer().catch(() => {});
}

/* ----------------- progress + auto refresh ----------------- */
let autoTimer = null;
let progressRAF = null;
let progressStart = null;

const setProgress = (pct) => { const b = $("topProgress"); if (b) b.style.width = `${clamp(pct, 0, 100).toFixed(2)}%`; };
const resetProgress = () => { progressStart = performance.now(); setProgress(0); };
const humanInterval = (ms) => (ms < 60000 ? `${Math.round(ms / 1000)}s` : `${Math.round(ms / 60000)}m`);

function updateAutoUI() {
  const on = !!autoTimer;
  const ms = num($("refreshEvery")?.value, 30000);
  setText("pollEvery", humanInterval(ms));
  setText("pollstate", on ? "running" : "stopped");
  if ($("toggleAuto")) $("toggleAuto").textContent = on ? "Stop" : "Start";
  setText("autoState", on ? "on" : "off");
}

function startAuto() {
  stopAuto();
  const ms = num($("refreshEvery")?.value, 30000);
  setIntervalStore(ms); setAuto(true);
  resetProgress(); refreshAllOnce().catch(() => {});
  autoTimer = setInterval(() => refreshAllOnce().catch(() => {}), ms);
  updateAutoUI();
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null; setAuto(false);
  updateAutoUI(); resetProgress(); setProgress(0);
}

function toggleAuto() { autoTimer ? stopAuto() : startAuto(); }

function startProgressLoop() {
  const step = () => {
    const on = !!autoTimer;
    const ms = num($("refreshEvery")?.value, 30000);
    if (!on) { setProgress(0); return (progressRAF = requestAnimationFrame(step)); }
    if (progressStart == null) progressStart = performance.now();
    setProgress(((performance.now() - progressStart) / ms) * 100);
    progressRAF = requestAnimationFrame(step);
  };
  if (!progressRAF) progressRAF = requestAnimationFrame(step);
}

/* ----------------- init ----------------- */
function debounce(fn, t = 150) { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), t); }; }

document.addEventListener("DOMContentLoaded", () => {
  initLedMeter();
  setLedMeter(0, "Collecting baseline…");
  startProgressLoop();

  if ($("pico")) $("pico").value = loadPico();

  $("save")?.addEventListener("click", () => {
    savePico(($("pico")?.value || "").trim());
    alert("Saved.");
  });

  $("refreshNow")?.addEventListener("click", () => refreshAllOnce().catch(() => {}));

  // theme
  let mode = getTheme() || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(mode);
  $("themeToggle")?.addEventListener("change", (e) => {
    const m = e.target.checked ? "dark" : "light";
    setTheme(m); applyTheme(m);
  });

  // auto refresh
  if ($("refreshEvery")) $("refreshEvery").value = String(getInterval());
  $("toggleAuto")?.addEventListener("click", toggleAuto);
  $("lang")?.addEventListener("change", (e) => { ls.set("co2_meter_lang", e.target.value); applyI18n(e.target.value); });
  const currentLang = ls.get("co2_meter_lang", "en"); if ($("lang")) $("lang").value = currentLang; applyI18n(currentLang);
  
  $("refreshEvery")?.addEventListener("change", () => {
    const ms = num($("refreshEvery")?.value, 30000);
    setIntervalStore(ms);
    updateAutoUI();
    autoTimer ? startAuto() : resetProgress();
  });

  window.addEventListener("resize", debounce(() => loadWindowFromServer().catch(() => {})));

  getAuto()
    ? startAuto()
    : (refreshAllOnce().catch(() => {}), updateAutoUI(), resetProgress(), setProgress(0));
});
