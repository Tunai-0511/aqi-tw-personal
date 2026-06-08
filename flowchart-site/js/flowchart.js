/* =============================================================================
 * flowchart.js — 傳統流程圖（直式：上→下流向 + 左側階段帶）
 * 對齊 run_pipeline()：開始 → 三代理人 → 輸出 → 完成。
 * 直式（高 > 寬，不再扁）；左側用顏色帶標示各代理人階段；點方框看 demo。
 * ========================================================================== */
(function (global) {
  "use strict";
  const L = global.LOBSTER;
  const C = L.C;

  let view, stage, svg, built = false;

  /* ── 階段（代理人）→ 顏色 / 標籤 ─────────────────────── */
  const PHASES = {
    user:      { label: "使用者 / 應用層", color: C.cyan },
    collector: { label: "① 採集者",        color: C.cyan },
    analyst:   { label: "② 分析師",        color: C.purple },
    advisor:   { label: "③ 預警員",        color: C.green },
    output:    { label: "外部服務 / 輸出", color: C.orange },
  };

  /* ── 步驟（由上到下；row = 陣列索引）─────────────────── */
  const STEPS = [
    { id: "start",  agent: "user",      type: "term", label: "開始" },
    { id: "launch", agent: "user",      type: "proc", label: "開啟頁面 · 啟動 Pipeline", demo: "app" },
    { id: "fetch",  agent: "collector", type: "proc", label: "抓取 EPA · 感測器 · 氣象", demo: "collector" },
    { id: "clean",  agent: "collector", type: "proc", label: "清洗去重 · 計數", demo: "collector" },
    { id: "dec1",   agent: "collector", type: "dec",  label: "資料<br>足夠?" },
    { id: "packet", agent: "collector", type: "proc", label: "資料封包 · 20 城市", demo: "collector" },
    { id: "risk",   agent: "analyst",   type: "proc", label: "加權風險公式", demo: "analyst" },
    { id: "ragllm", agent: "analyst",   type: "proc", label: "RAG 檢索 + LLM 生成", demo: "rag" },
    { id: "grade",  agent: "analyst",   type: "proc", label: "風險分級", demo: "analyst" },
    { id: "groups", agent: "advisor",   type: "proc", label: "個人化 safe_hours", demo: "advisor" },
    { id: "advice", agent: "advisor",   type: "proc", label: "個人化健康建議", demo: "advisor" },
    { id: "store",  agent: "output",    type: "proc", label: "寫入 SQLite 時序快取", demo: "sqlite" },
    { id: "export", agent: "output",    type: "proc", label: "匯出 latest_aqi.json", demo: "export" },
    { id: "done",   agent: "output",    type: "term", label: "完成" },
  ];
  const rowOf = {}; STEPS.forEach((s, i) => (rowOf[s.id] = i));
  const stepById = {}; STEPS.forEach((s) => (stepById[s.id] = s));

  const LINKS = [
    { f: "start", t: "launch" }, { f: "launch", t: "fetch" }, { f: "fetch", t: "clean" },
    { f: "clean", t: "dec1" },
    { f: "dec1", t: "packet", label: "是" },     // 通過 → 往下
    { f: "dec1", t: "clean", label: "否", back: true }, // 不足 → 右側繞回重抓
    { f: "packet", t: "risk" }, { f: "risk", t: "ragllm" }, { f: "ragllm", t: "grade" },
    { f: "grade", t: "groups" }, { f: "groups", t: "advice" }, { f: "advice", t: "store" },
    { f: "store", t: "export" }, { f: "export", t: "done" },
  ];

  /* ── 版面（直式）─────────────────────────────────────── */
  const LAY = { padTop: 26, rowH: 92, phaseW: 128, gap: 26, boxW: 256, rightPad: 92,
                procH: 56, termW: 150, termH: 48, decW: 92, decH: 84 };
  const colLeft = LAY.phaseW + LAY.gap;
  const colCX = colLeft + LAY.boxW / 2;
  const loopX = colLeft + LAY.boxW + 48;          // 「否」回饋線的右側垂直線
  const stageW = () => LAY.phaseW + LAY.gap + LAY.boxW + LAY.rightPad;
  const stageH = () => LAY.padTop * 2 + STEPS.length * LAY.rowH;

  function dims(s) {
    if (s.type === "term") return { w: LAY.termW, h: LAY.termH };
    if (s.type === "dec")  return { w: LAY.decW + 56, h: LAY.decH };
    return { w: LAY.boxW, h: LAY.procH };
  }
  function rect(s) {
    const d = dims(s);
    const cy = LAY.padTop + rowOf[s.id] * LAY.rowH + LAY.rowH / 2;
    return { cx: colCX, cy, w: d.w, h: d.h, left: colCX - d.w / 2, right: colCX + d.w / 2, top: cy - d.h / 2, bottom: cy + d.h / 2 };
  }

  /* =======================================================================
   * 建 DOM
   * ==================================================================== */
  function build() {
    view = document.getElementById("flow-view");
    view.innerHTML = `
      <div class="flow-head">
        <h1>📋 LobsterAQI Pipeline 流程圖 <span class="fc-sub">直式 · 分階段</span></h1>
        <p>對齊 <code>run_pipeline()</code>：由上而下，左側色帶為各代理人階段。點任一方框看該環節 demo。</p>
      </div>
      <div id="flow-stage"></div>`;
    stage = document.getElementById("flow-stage");
    stage.style.width = stageW() + "px";
    stage.style.height = stageH() + "px";

    // 左側階段帶（把連續同代理人的步驟群成一段）
    const groups = [];
    STEPS.forEach((s, i) => {
      const last = groups[groups.length - 1];
      if (last && last.agent === s.agent) last.end = i;
      else groups.push({ agent: s.agent, start: i, end: i });
    });
    groups.forEach((g) => {
      const ph = PHASES[g.agent];
      const top = LAY.padTop + g.start * LAY.rowH + 6;
      const h = (g.end - g.start + 1) * LAY.rowH - 12;
      const band = document.createElement("div");
      band.className = "flow-phase";
      band.style.top = top + "px"; band.style.height = h + "px"; band.style.width = LAY.phaseW + "px";
      band.style.setProperty("--fc", ph.color);
      band.innerHTML = `<span>${ph.label}</span>`;
      stage.appendChild(band);
    });

    // SVG 連線層
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "flow-svg");
    svg.setAttribute("width", stageW()); svg.setAttribute("height", stageH());
    svg.setAttribute("viewBox", `0 0 ${stageW()} ${stageH()}`);
    stage.appendChild(svg);

    // 步驟方框
    STEPS.forEach((s) => {
      const ph = PHASES[s.agent];
      const r = rect(s);
      const el = document.createElement("div");
      el.className = "flow-box " + s.type + (s.demo ? " clickable" : "");
      el.id = "fc-" + s.id;
      el.style.left = r.left + "px"; el.style.top = r.top + "px";
      el.style.width = r.w + "px"; el.style.height = r.h + "px";
      el.style.setProperty("--fc", ph.color);
      el.innerHTML = s.type === "dec"
        ? `<span class="dec-shape"></span><span class="flow-tx">${s.label}</span>`
        : `<span class="flow-tx">${s.label}</span>`;
      if (s.demo) el.addEventListener("click", () => { if (global.LOBSTER_MAIN) global.LOBSTER_MAIN.openPanel(s.demo); });
      stage.appendChild(el);
    });

    drawArrows();
    built = true;
  }

  /* ── 連線（直式：往下直線；「否」走右側乾淨繞回）──────── */
  function drawArrows() {
    let html = `<defs>
      <marker id="fc-ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
        <path d="M0,1 L9,5 L0,9 L2.4,5 z" fill="#8fa6c8"/></marker>
      <marker id="fc-ar-no" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
        <path d="M0,1 L9,5 L0,9 L2.4,5 z" fill="${C.red}"/></marker>
      </defs>`;

    LINKS.forEach((lk) => {
      const a = rect(stepById[lk.f]), b = rect(stepById[lk.t]);
      let d, lx, ly, col = "#8fa6c8", mk = "url(#fc-ar)";
      if (lk.back) {
        // 否：從 dec 右緣 → 右 → 上 → 回到目標右緣（在右側，不疊到中央主線）
        col = C.red; mk = "url(#fc-ar-no)";
        d = `M${a.right},${a.cy} L${loopX},${a.cy} L${loopX},${b.cy} L${b.right},${b.cy}`;
        lx = loopX + 12; ly = (a.cy + b.cy) / 2;
      } else {
        // 主線：上方框底 → 下方框頂（同一中軸 → 垂直直線）
        d = `M${a.cx},${a.bottom} L${b.cx},${b.top}`;
        lx = a.cx + 13; ly = (a.bottom + b.top) / 2 + 4;
      }
      html += `<path class="fc-line${lk.back ? " back" : ""}" d="${d}" stroke="${col}" stroke-width="2.2" fill="none" marker-end="${mk}"/>`;
      if (lk.label) {
        const cls = lk.back ? "no" : "yes";
        html += `<text class="fc-elabel ${cls}" x="${lx}" y="${ly}" text-anchor="${lk.back ? "start" : "start"}">${lk.label}</text>`;
      }
    });
    svg.innerHTML = html;
  }

  /* =======================================================================
   * 對外：顯示 + pipeline 高亮
   * ==================================================================== */
  function show() { if (!built) build(); view.classList.remove("hidden"); }
  function hide() { if (view) view.classList.add("hidden"); }
  function isVisible() { return view && !view.classList.contains("hidden"); }

  function highlightAgent(id) {
    if (!built) return;
    STEPS.forEach((s) => {
      const el = document.getElementById("fc-" + s.id);
      if (el) el.classList.toggle("active", s.agent === id);
    });
  }
  function markStep(stepId, cls) {
    const el = document.getElementById("fc-" + stepId);
    if (el) { el.classList.remove("active", "done"); if (cls) el.classList.add(cls); }
  }
  function reset() {
    if (!built) return;
    STEPS.forEach((s) => { const el = document.getElementById("fc-" + s.id); if (el) el.classList.remove("active", "done"); });
  }

  global.LOBSTER_FLOW = { build, show, hide, isVisible, highlightAgent, markStep, reset };
})(window);
