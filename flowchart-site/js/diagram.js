/* =============================================================================
 * diagram.js — 分層架構圖視圖（比照參考圖）
 * 負責：建 DOM、畫 SVG 資料流連線（含流動動畫）、滑鼠 3D 視差、點卡片開 demo、
 *       以及對外的 pipeline 進度 API（高亮當前 agent / 子步驟）。
 * ========================================================================== */
(function (global) {
  "use strict";
  const L = global.LOBSTER;
  const D = L.DIAGRAM;
  const C = L.C;

  let root, svg, tilt, view, built = false;

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* 連線色（對齊圖例）：即時=cyan / LLM=purple / Hermes 拉取=purple / 儲存=green */
  const FLOWC = { data: C.cyan, ctrl: C.cyan, llm: C.purple, pull: C.purple, store: C.green };
  const FLOWDASH = { llm: true, pull: true, store: true };

  const CONN = [
    { f: "blk-user", fs: "bottom", t: "blk-app", ts: "top", k: "data", bidir: true },
    { f: "blk-app", fs: "bottom", t: "agent-collector", ts: "top", k: "ctrl" },
    { f: "src-epa", fs: "right", t: "pipeline-band", ts: "left", k: "data", matchY: true },
    { f: "src-civic", fs: "right", t: "pipeline-band", ts: "left", k: "data", matchY: true },
    { f: "src-lass", fs: "right", t: "pipeline-band", ts: "left", k: "data", matchY: true },
    { f: "src-openmeteo", fs: "right", t: "pipeline-band", ts: "left", k: "data", matchY: true },
    { f: "src-cams", fs: "right", t: "pipeline-band", ts: "left", k: "data", matchY: true },
    // 服務側鏡像資料源側:從服務水平連到 pipeline-band(matchY)→ 直線、與三代理人對齊
    { f: "svc-llm", fs: "left", t: "pipeline-band", ts: "right", k: "llm", matchY: true, bidir: true },
    { f: "svc-hermes", fs: "left", t: "pipeline-band", ts: "right", k: "pull", matchY: true, bidir: true },
    { f: "pipeline-band", fs: "bottom", t: "blk-storage", ts: "top", k: "store" },
  ];
  const connPaths = {}; // "f>t" -> { base, flow }

  /* =======================================================================
   * 建 DOM
   * ==================================================================== */
  function build() {
    view = document.getElementById("diagram-view");
    root = document.getElementById("diagram");
    tilt = document.getElementById("diagram-tilt");
    root.innerHTML = template();
    // 進場 stagger：同步（首次繪製前）設好 animation-delay
    root.querySelectorAll(".dg-anim").forEach((el, i) => { el.style.animationDelay = (i * 40) + "ms"; });
    svg = document.getElementById("connectors");

    // 點卡片 → 開 demo
    root.addEventListener("click", (e) => {
      const el = e.target.closest("[data-demo]");
      if (el && global.LOBSTER_MAIN) global.LOBSTER_MAIN.openPanel(el.dataset.demo);
    });

    bindTilt();
    window.addEventListener("resize", debounce(drawConnectors, 150));
    built = true;
    // 版面定位完成後再畫連線（進場動畫由純 CSS 處理）
    requestAnimationFrame(drawConnectors);
  }

  function template() {
    return `
      <div class="dg-title dg-anim">
        <h1><span class="lob">🦞</span> Lobster<span class="accent">AQI</span> 系統架構流程圖</h1>
        <p>多代理人協作的台灣空氣品質監控與健康預警平台</p>
      </div>
      <svg id="connectors" xmlns="http://www.w3.org/2000/svg"></svg>

      <!-- 用戶層 -->
      <div class="dg-row">
        <div class="layer-label dg-anim"><span class="ic">👥</span><span class="tx">用戶層</span></div>
        <div class="group-box user-browser card3d clickable dg-anim" id="blk-user" data-demo="user" style="flex:1">
          <div class="gb-title">🖥️ 使用者瀏覽器 <span class="sub">(localhost:8501)</span></div>
          <div class="user-grid">
            ${D.userItems.map((u) => `
              <div class="user-item"><span class="ic">${u.icon}</span><span class="nm">${esc(u.name)}</span>${u.sub ? `<span class="sb">${esc(u.sub)}</span>` : ""}</div>`).join("")}
          </div>
        </div>
      </div>

      <!-- 應用層:獨立全寬一列(移出三欄)→ 讓「資料源 / 三代理人 / 服務」三欄頂部對齊,連線才水平直 -->
      <div class="app-layer card3d dg-anim" id="blk-app">
        <div class="gb-title">🖥️ LobsterAQI Streamlit 應用層</div>
        <div class="app-boxes">
          ${D.appBoxes.map((b) => `
            <div class="app-box clickable" data-demo="${b.demo}"><div class="nm">${esc(b.name)}</div><div class="sb">${esc(b.sub)}</div></div>`).join("")}
        </div>
      </div>

      <!-- 主三欄:資料源 | 三代理人 Pipeline | 服務(頂部對齊 → 連線水平) -->
      <div class="dg-main">
        <!-- 左：外部資料來源 -->
        <div class="dg-col dg-anim">
          <div class="col-title">外部資料來源</div>
          <div class="src-stack">
            ${D.sources.map((s) => `
              <div class="src-card card3d clickable" id="src-${s.id}" data-demo="${s.demo}">
                <span class="ic">${s.icon}</span>
                <div><div class="nm">${esc(s.name)}</div>${s.lines.map((l) => `<div class="ln">${esc(l)}</div>`).join("")}</div>
              </div>`).join("")}
          </div>
        </div>

        <!-- 中：三代理人 Pipeline -->
        <div class="center-col">
          <div class="pipeline-band dg-anim" id="pipeline-band">
            <div class="band-label"><span class="bot">🤖</span><span class="vtx">三代理人 Pipeline</span></div>
            <div class="agents">
              ${D.agents.map((a) => agentCard(a)).join("")}
            </div>
          </div>
        </div>

        <!-- 右：外部服務整合 -->
        <div class="dg-col dg-anim">
          <div class="col-title svc">外部服務整合</div>
          <div class="svc-stack">
            ${D.services.map((s) => `
              <div class="svc-card card3d clickable" id="svc-${s.id}" data-demo="${s.demo}" style="--sc:${s.color}">
                <div class="svc-head"><span class="ic">${s.icon}</span><span class="nm">${esc(s.name)}</span><span class="tag">${esc(s.tag)}</span></div>
                <ul>${s.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>
                ${s.note ? `<div class="svc-note">${esc(s.note)}</div>` : ""}
              </div>`).join("")}
          </div>
        </div>
      </div>

      <!-- 儲存層 -->
      <div class="dg-row">
        <div class="layer-label dg-anim"><span class="ic">🗄️</span><span class="tx">資料儲存層</span></div>
        <div class="group-box storage-box card3d clickable dg-anim" id="blk-storage" data-demo="sqlite" style="flex:1">
          <div class="gb-title">🗄️ SQLite 本機時序資料庫 <span class="sub">(./lobster_aqi.sqlite)</span></div>
          <div class="storage-grid">
            ${D.storage.map((s) => `<div class="storage-item">${esc(s)}</div>`).join("")}
          </div>
        </div>
      </div>

      <!-- 頁尾 -->
      <div class="dg-footer">
        <div class="dg-foot-box dg-anim">
          <h4>資料流向說明</h4>
          <div class="legend-flows">
            ${D.flows.map((f) => `<div class="legend-flow" style="--fc:${f.color}"><span class="ln ${f.dashed ? "dash" : ""}"></span>${esc(f.name)}</div>`).join("")}
          </div>
        </div>
        <div class="dg-foot-box dg-anim">
          <h4>系統特色</h4>
          <div class="feature-row">
            ${D.features.map((f) => `<div class="feature-chip"><span class="ic">${f.icon}</span>${esc(f.name)}</div>`).join("")}
          </div>
        </div>
      </div>`;
  }

  function agentCard(a) {
    return `
      <div class="agent-card card3d clickable" id="agent-${a.id}" data-demo="${a.demo}" style="--ac:${a.color}">
        <div class="agent-top">
          <span class="agent-num">${a.num}</span>
          <span class="agent-icn">${stepEmojiHead(a.id)}</span>
          <div class="agent-titles">
            <div class="en">${esc(a.en)} <span class="zh">${esc(a.name)}</span></div>
            <div class="tag">${esc(a.tagline)}</div>
          </div>
        </div>
        <div class="agent-bottom">
          <div class="agent-steps">
            ${a.steps.map((s, i) => `<div class="step-chip" data-step="${i}"><span class="ic">${s.icon}</span><span class="nm">${esc(s.name)}</span></div>`).join("")}
          </div>
          <div class="agent-out">
            <div class="oh">輸出</div>
            <ul>${a.outputs.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>
          </div>
        </div>
      </div>`;
  }
  function stepEmojiHead(id) { return { collector: "📥", analyst: "🧠", advisor: "🔔" }[id] || "🤖"; }

  /* =======================================================================
   * SVG 連線
   * ==================================================================== */
  function rectIn(el, cRect) {
    const r = el.getBoundingClientRect();
    return {
      left: r.left - cRect.left, top: r.top - cRect.top,
      right: r.right - cRect.left, bottom: r.bottom - cRect.top,
      cx: r.left - cRect.left + r.width / 2, cy: r.top - cRect.top + r.height / 2,
    };
  }
  function anchor(r, side) {
    if (side === "top") return { x: r.cx, y: r.top };
    if (side === "bottom") return { x: r.cx, y: r.bottom };
    if (side === "left") return { x: r.left, y: r.cy };
    return { x: r.right, y: r.cy }; // right
  }
  function pathD(a, b, fs, ts, ra, rb, matchY) {
    let p1 = anchor(ra, fs), p2 = anchor(rb, ts);
    if (matchY) { p2 = { x: p2.x, y: Math.max(rb.top + 8, Math.min(rb.bottom - 8, p1.y)) }; }
    if (fs === "bottom" && ts === "top") {
      const my = (p1.y + p2.y) / 2;
      return `M${p1.x},${p1.y} L${p1.x},${my} L${p2.x},${my} L${p2.x},${p2.y}`;
    }
    if (fs === "right" && ts === "left") {
      // 幾乎同高 → 直線；否則轉彎點靠近目標 → 水平線拉長、走向直、不互相擠
      if (Math.abs(p1.y - p2.y) < 8) return `M${p1.x},${p1.y} L${p2.x},${p2.y}`;
      const bx = Math.max(p1.x + 16, p2.x - 24);
      return `M${p1.x},${p1.y} L${bx},${p1.y} L${bx},${p2.y} L${p2.x},${p2.y}`;
    }
    if (fs === "bottom" && (ts === "left" || ts === "right")) {
      return `M${p1.x},${p1.y} L${p1.x},${p2.y} L${p2.x},${p2.y}`;
    }
    return `M${p1.x},${p1.y} L${p2.x},${p2.y}`;
  }

  function drawConnectors() {
    if (!built) return;
    const prevT = tilt.style.transform;
    tilt.style.transform = "none"; // 量測前先攤平，避免傾斜影響座標
    const cRect = root.getBoundingClientRect();
    const W = root.scrollWidth, H = root.scrollHeight;
    svg.setAttribute("width", W); svg.setAttribute("height", H);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

    // markers
    let defs = `<defs>`;
    Object.keys(FLOWC).forEach((k) => {
      // 大箭頭（固定像素大小）→ 走向清楚
      defs += `<marker id="ar-${k}" viewBox="0 0 10 10" refX="7.5" refY="5" markerWidth="14" markerHeight="14" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
        <path d="M0,0.5 L10,5 L0,9.5 L2.6,5 z" fill="${FLOWC[k]}"/></marker>`;
    });
    defs += `</defs>`;

    let html = defs;
    CONN.forEach((c) => {
      const ea = document.getElementById(c.f), eb = document.getElementById(c.t);
      if (!ea || !eb) return;
      const ra = rectIn(ea, cRect), rb = rectIn(eb, cRect);
      const d = pathD(c.f, c.t, c.fs, c.ts, ra, rb, c.matchY);
      const col = FLOWC[c.k], dash = FLOWDASH[c.k];
      const mEnd = `marker-end="url(#ar-${c.k})"`;
      const mStart = c.bidir ? `marker-start="url(#ar-${c.k})"` : "";
      const baseDash = dash ? `stroke-dasharray="7 7"` : "";
      html += `<path class="conn-base" data-key="${c.f}>${c.t}" d="${d}" stroke="${col}" stroke-width="2.2" ${baseDash} ${mEnd} ${mStart}></path>`;
    });
    svg.innerHTML = html;
    // 快取以供 pipeline 高亮(只剩單一靜態 base 線,無無止盡動畫)
    svg.querySelectorAll(".conn-base").forEach((p) => { connPaths[p.dataset.key] = connPaths[p.dataset.key] || {}; connPaths[p.dataset.key].base = p; });
    tilt.style.transform = prevT || "";
  }

  /* =======================================================================
   * 3D 視差 + 進場
   * ==================================================================== */
  function bindTilt() {
    let raf = 0;
    view.addEventListener("mousemove", (e) => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const rx = (e.clientY / window.innerHeight - 0.5) * -2.0;
        const ry = (e.clientX / window.innerWidth - 0.5) * 2.4;
        tilt.style.transform = `rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg)`;
      });
    });
    view.addEventListener("mouseleave", () => { tilt.style.transform = "rotateX(0deg) rotateY(0deg)"; });
  }

  /* =======================================================================
   * 對外：顯示切換 + pipeline 進度 API
   * ==================================================================== */
  function show() {
    if (!built) build();
    view.classList.remove("hidden");
    requestAnimationFrame(drawConnectors);
  }
  function hide() { if (view) view.classList.add("hidden"); }
  function isVisible() { return view && !view.classList.contains("hidden"); }

  function highlightAgent(id) {
    if (!built) return;
    ["collector", "analyst", "advisor"].forEach((a) => {
      const el = document.getElementById("agent-" + a);
      if (el) el.classList.toggle("active", a === id);
    });
    const el = document.getElementById("agent-" + id);
    // 只在該 agent 不在可視範圍內才捲動（不強制把畫面拉走）
    if (el && isVisible()) {
      const r = el.getBoundingClientRect();
      if (r.top < 90 || r.bottom > window.innerHeight - 20) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }
  function stepState(agentId, idx, cls) {
    const card = document.getElementById("agent-" + agentId);
    if (!card) return;
    const chip = card.querySelector(`.step-chip[data-step="${idx}"]`);
    if (chip) { chip.classList.remove("active", "done"); if (cls) chip.classList.add(cls); }
  }
  function markAgentDone(id) {
    const el = document.getElementById("agent-" + id);
    if (el) el.classList.remove("active");
  }
  function boostFlow(f, t, on) {
    const p = connPaths[f + ">" + t];
    if (!p || !p.base) return;
    p.base.classList.toggle("boost", !!on);
    p.base.style.strokeWidth = on ? "5" : "";
    p.base.style.filter = on ? "drop-shadow(0 0 6px currentColor)" : "";
  }
  function resetPipeline() {
    if (!built) return;
    ["collector", "analyst", "advisor"].forEach((a) => {
      const el = document.getElementById("agent-" + a);
      if (el) { el.classList.remove("active"); el.querySelectorAll(".step-chip").forEach((c) => c.classList.remove("active", "done")); }
    });
    Object.values(connPaths).forEach((p) => { if (p.base) { p.base.classList.remove("boost"); p.base.style.strokeWidth = ""; p.base.style.filter = ""; } });
  }

  function debounce(fn, ms) { let t; return function () { clearTimeout(t); t = setTimeout(fn, ms); }; }

  global.LOBSTER_DIAGRAM = {
    build, show, hide, isVisible,
    highlightAgent, stepState, markAgentDone, boostFlow, resetPipeline,
    redraw: drawConnectors,
  };
})(window);
