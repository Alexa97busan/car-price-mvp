const $ = (sel) => document.querySelector(sel);
const fmt = (n) => Number(n).toLocaleString("ko-KR");

let DATA = null;   // {stats, options, meta}
let state = { model: "QM6", year: 2021, km: 70000, trim: "all", price: null, opts: new Set() };
let hadYearParam = false;

async function load() {
  const [stats, options, meta] = await Promise.all([
    fetch("data/stats.json").then(r => r.json()),
    fetch("data/options.json").then(r => r.json()),
    fetch("data/meta.json").then(r => r.json()),
  ]);
  DATA = { stats, options, meta };
}

function modelData() {
  return DATA.stats.models.find(m => m.key === state.model) || DATA.stats.models[0];
}

function readParams() {
  const q = new URLSearchParams(location.search);
  hadYearParam = q.get("y") != null;
  if (q.get("m")) state.model = q.get("m");
  if (q.get("y")) state.year = Number(q.get("y"));
  if (q.get("km")) state.km = Number(q.get("km"));
  if (q.get("t")) state.trim = q.get("t");
  if (q.get("p")) state.price = Number(q.get("p"));
  if (q.get("o")) state.opts = new Set(q.get("o").split(",").filter(Boolean));
}

function writeParams() {
  const q = new URLSearchParams();
  q.set("m", state.model);
  q.set("y", state.year);
  q.set("km", state.km);
  if (state.trim !== "all") q.set("t", state.trim);
  if (state.price) q.set("p", state.price);
  if (state.opts.size) q.set("o", [...state.opts].join(","));
  history.replaceState(null, "", "?" + q.toString());
}

function fillModels() {
  const sel = $("#model");
  sel.innerHTML = DATA.stats.models.map(m =>
    `<option value="${m.key}">${m.name}</option>`).join("");
  sel.value = state.model;
}

function yearsOf(md) {
  return Object.keys(md.years).map(Number).sort((a, b) => b - a);
}

function fillYears(preferGood = false) {
  const md = modelData();
  const years = yearsOf(md);
  const cur = md.years[state.year];
  if (!years.includes(state.year) || (preferGood && (!cur || cur.n < 10))) {
    const good = years.filter(y => md.years[y].n >= 10);
    state.year = good.length ? good[0] : years[0];
  }
  $("#year").innerHTML = years.map(y => {
    const s = md.years[y];
    const tag = s.n < 10 ? " · 표본 적음" : "";
    return `<option value="${y}">${y}년${tag}</option>`;
  }).join("");
  $("#year").value = String(state.year);
}

function fillTrims() {
  const md = modelData();
  const ys = md.years[state.year];
  const trims = ys.trims || {};
  const keys = Object.keys(trims).filter(t => trims[t].n >= 5)
    .sort((a, b) => trims[b].n - trims[a].n);
  if (state.trim !== "all" && !keys.includes(state.trim)) state.trim = "all";
  $("#trim").innerHTML = `<option value="all">전체 트림</option>` +
    keys.map(t => `<option value="${t}">${t} (${trims[t].n}대)</option>`).join("");
  $("#trim").value = state.trim;
}

function fillOptions() {
  const md = modelData();
  const list = $("#optList");
  list.innerHTML = DATA.options.codes.map(o => {
    const r = DATA.options.take_rates[o.code]?.[state.model];
    const pct = r ? r.pct : null;
    const checked = state.opts.has(o.code) ? "checked" : "";
    return `<label><input type="checkbox" value="${o.code}" ${checked}>
      ${o.name}<span class="rate">${pct === null ? "" : pct + "%"}</span></label>`;
  }).join("");
  list.querySelectorAll("input").forEach(cb => {
    cb.addEventListener("change", () => {
      if (cb.checked) state.opts.add(cb.value); else state.opts.delete(cb.value);
      $("#optCount").textContent = state.opts.size + "개";
      writeParams();
    });
  });
  $("#optCount").textContent = state.opts.size + "개";
}

function confidenceOf(n) {
  if (n >= 30) return { label: "높음", cls: "good" };
  if (n >= 10) return { label: "중간", cls: "warn" };
  return { label: "낮음", cls: "bad" };
}

function compute() {
  const md = modelData();
  const ys = md.years[state.year];
  if (!ys) return null;

  const hasTrim = state.trim !== "all" && ys.trims?.[state.trim]?.n >= 5;
  const base = hasTrim ? ys.trims[state.trim] : ys;

  const km = Number.isFinite(state.km) ? state.km : base.median_km;
  let adj = (md.km_slope_per_10k * (km - base.median_km)) / 10000;
  const cap = base.median * 0.15;
  adj = Math.max(-cap, Math.min(cap, adj));

  const out = {
    md, ys, hasTrim, base, km, adj,
    median: Math.round(base.median + adj),
    p25: Math.round(base.p25 + adj),
    p75: Math.round(base.p75 + adj),
    p10: Math.round((base.p10 ?? base.p25 - 300) + adj),
    p90: Math.round((base.p90 ?? base.p75 + 300) + adj),
    n: base.n,
    medianKm: base.median_km,
  };
  out.conf = confidenceOf(out.n);
  out.residual = md.new_price_ref ? Math.round(out.median / md.new_price_ref * 100) : null;
  return out;
}

function verdictOf(c, price) {
  if (!price) return null;
  if (price < c.p25) return { key: "bargain", label: "급매" };
  if (price > c.p75) return { key: "expensive", label: "비쌈" };
  return { key: "fair", label: "적정" };
}

function render() {
  const c = compute();
  if (!c) return;
  const md = c.md;

  const verdict = verdictOf(c, state.price);
  const vEl = $("#verdict");
  if (verdict) {
    vEl.className = "verdict " + verdict.key;
    vEl.textContent = verdict.label;
  } else {
    vEl.className = "verdict hidden";
  }

  $("#median").textContent = fmt(c.median) + "만 원";
  const trimTxt = c.hasTrim ? state.trim + " 트림" : "전체 트림";
  $("#medianSub").textContent =
    `${state.year}년식 ${trimTxt} · ${fmt(c.km)}km${c.hasTrim ? "" : " 기준"}`;

  // range bar (p10..p90)
  const span = Math.max(1, c.p90 - c.p10);
  const pos = v => Math.max(0, Math.min(100, (v - c.p10) / span * 100));
  const band = $("#band");
  band.style.left = pos(c.p25) + "%";
  band.style.width = Math.max(2, pos(c.p75) - pos(c.p25)) + "%";
  $("#medianMark").style.left = pos(c.median) + "%";
  const pm = $("#priceMark");
  if (state.price) {
    pm.classList.remove("hidden");
    pm.style.left = pos(state.price) + "%";
  } else {
    pm.classList.add("hidden");
  }
  $("#rangeScale").innerHTML =
    `<span>${fmt(c.p10)}만</span><span>P25 ${fmt(c.p25)} · P75 ${fmt(c.p75)}</span><span>${fmt(c.p90)}만</span>`;

  $("#sampleN").textContent = c.n + "대";
  $("#confidence").textContent = c.conf.label;
  $("#confidence").style.color = c.conf.cls === "good" ? "var(--good)" : c.conf.cls === "warn" ? "var(--warn)" : "var(--bad)";
  const sign = c.adj >= 0 ? "+" : "";
  $("#kmAdj").textContent = sign + Math.round(c.adj) + "만";
  $("#residual").textContent = c.residual === null ? "—" : c.residual + "%";
  $("#residual").title = md.new_price_note || "";

  // histogram (year-level distribution)
  const bins = c.ys.bins || [];
  const maxC = Math.max(1, ...bins.map(b => b.count));
  $("#hist").innerHTML = bins.map(b => {
    const hl = c.median >= b.from && c.median < b.to ? "hl" : "";
    const h = Math.max(4, Math.round(b.count / maxC * 100));
    return `<div class="${hl}" style="height:${h}%" title="${b.from}~${b.to}만: ${b.count}대"></div>`;
  }).join("");
  if (bins.length) {
    $("#histScale").innerHTML = `<span>${fmt(bins[0].from)}만</span><span>${fmt(bins[bins.length - 1].to)}만</span>`;
  }

  const notes = [];
  if (!c.hasTrim) notes.push("트림 표본이 부족해 전체 트림 기준으로 계산했습니다.");
  if (c.hasTrim) notes.push("가격 분포 막대는 전체 트림 기준입니다.");
  if (c.n < 10) notes.push("표본이 10대 미만이라 참고용입니다.");
  notes.push("등록 호가 기준 · 실계약은 3~10% 낮을 수 있습니다.");
  $("#calcNote").textContent = notes.join(" ");

  $("#stickyVerdict").textContent =
    (verdict ? verdict.label + " · " : "") + fmt(c.median) + "만";
  $("#stickyRange").textContent = `${fmt(c.p25)}~${fmt(c.p75)}만`;

  writeParams();
}

function renderOptionStats() {
  const md = modelData();
  const rows = DATA.options.codes
    .map(o => ({ o, r: DATA.options.take_rates[o.code]?.[state.model] }))
    .filter(x => x.r)
    .sort((a, b) => b.r.pct - a.r.pct)
    .slice(0, 8);
  $("#optStats").innerHTML = rows.map(({ o, r }) => `
    <div class="stat-row">
      <span class="nm">${o.name}</span>
      <span class="track"><i style="width:${r.pct}%"></i></span>
      <span class="pct">${r.pct}%</span>
    </div>`).join("");
}

function renderMeta() {
  const total = DATA.stats.models.reduce((s, m) => s + m.total, 0);
  $("#metaLine").textContent = `데이터 ${DATA.meta.snapshot} · QM6 436대 · SM6 231대 · 총 ${fmt(total)}대`;
  $("#snapshotDate").textContent = DATA.meta.snapshot;
  $("#notice").innerHTML = DATA.meta.notes.map(n => `<p>· ${n}</p>`).join("");
}

function bind() {
  $("#model").addEventListener("change", (e) => {
    state.model = e.target.value;
    state.trim = "all";
    fillYears(true); fillTrims(); fillOptions(); renderOptionStats(); render();
  });
  $("#year").addEventListener("change", (e) => {
    state.year = Number(e.target.value);
    fillTrims();
    const ys = modelData().years[state.year];
    if (!Number.isFinite(state.km) || state.km === 0) state.km = ys.median_km;
    render();
  });
  $("#trim").addEventListener("change", (e) => {
    state.trim = e.target.value;
    render();
  });
  const km = $("#km"), kmRange = $("#kmRange");
  km.addEventListener("input", () => {
    const v = Math.max(0, Math.min(300000, Number(km.value) || 0));
    state.km = v;
    kmRange.value = v;
    render();
  });
  kmRange.addEventListener("input", () => {
    state.km = Number(kmRange.value);
    km.value = state.km;
    render();
  });
  $("#price").addEventListener("input", (e) => {
    const v = Number(e.target.value);
    state.price = Number.isFinite(v) && v > 0 ? v : null;
    render();
  });
  $("#shareBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      $("#shareBtn").textContent = "링크 복사됨 ✓";
      setTimeout(() => { $("#shareBtn").textContent = "조건 링크 복사"; }, 1600);
    } catch {
      prompt("아래 링크를 복사하세요", location.href);
    }
  });
}

async function main() {
  await load();
  readParams();
  fillModels();
  fillYears(!hadYearParam);
  fillTrims();
  fillOptions();
  renderMeta();
  renderOptionStats();
  $("#km").value = state.km;
  $("#kmRange").value = state.km;
  $("#price").value = state.price || "";
  bind();
  render();
}

main().catch(err => {
  console.error(err);
  $("#metaLine").textContent = "데이터를 불러오지 못했습니다.";
  $("#median").textContent = "—";
});
