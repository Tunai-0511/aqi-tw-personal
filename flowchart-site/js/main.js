/* =============================================================================
 * main.js — 接線：雙視圖切換 / demo 面板 / tooltip / 統一的 Pipeline 進度動畫
 * 預設視圖 = 分層架構圖；3D 場景延遲初始化（第一次切換才建）。
 * ========================================================================== */
(function (global) {
  "use strict";
  const L = global.LOBSTER;
  const S = global.LOBSTER_SCENE;
  const DG = global.LOBSTER_DIAGRAM;
  const FLOW = global.LOBSTER_FLOW;
  const DEMOS = global.LOBSTER_DEMOS;

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  // 可暫停的 sleep：時間到後，若處於暫停狀態就等到「繼續」才往下走
  let pipePaused = false;
  const pauseWaiters = new Set();
  const sleep = (ms) => new Promise((resolve) => {
    setTimeout(() => { if (!pipePaused) resolve(); else pauseWaiters.add(resolve); }, ms);
  });
  function setPaused(p) {
    pipePaused = p;
    const b = $("#btn-pause"); if (!b) return;
    if (p) {
      if (sceneReady) S.setFrozen(true);   // 凍結 3D 場景：封包停在半空，鏡頭仍可轉
      b.innerHTML = '▶ <span class="btn-full">繼續</span>'; b.classList.add("active");
      setSub('<span class="hl">⏸ 已暫停</span> · 封包停在當下，可旋轉/縮放查看');
    } else {
      if (sceneReady) S.setFrozen(false);
      b.innerHTML = '⏸ <span class="btn-full">暫停</span>'; b.classList.remove("active");
      const w = [...pauseWaiters]; pauseWaiters.clear(); w.forEach((r) => r()); // 喚醒等待中的 sleep
    }
  }
  function togglePause() { if (running) setPaused(!pipePaused); }

  let currentView = "diagram";
  let sceneReady = false;

  /* ── 啟動 ───────────────────────────────────────────── */
  function boot() {
    try {
      DG.build();          // 預設先建架構圖
      DG.show();
    } catch (err) {
      console.error(err);
      $("#loader").innerHTML = '<div class="loader-lobster">🦞</div><div class="loader-title">載入失敗</div><div class="loader-sub">' + (err && err.message || "") + '</div>';
      return;
    }
    $("#legend").classList.add("hidden"); // 圖例只在 3D 場景顯示
    wirePanel(); wireToolbar(); wireViewSwitch(); wireLog(); wireTheme();
    // 場景的 hover/click 回呼可先註冊（場景未建前不會觸發）
    S.onHover(onSceneHover);
    S.onClick((id) => openPanel(id));

    const loader = $("#loader");
    setTimeout(() => { loader.classList.add("gone"); setTimeout(() => loader.remove(), 700); }, 500);
  }

  function ensureScene() {
    if (sceneReady) return;
    if (!global.THREE) return;
    S.init();
    sceneReady = true;
    S.setTheme(document.body.classList.contains("light")); // 套用目前主題到場景
  }

  /* ── 深色 / 淺色主題切換 ────────────────────────────── */
  function wireTheme() {
    let light = false;
    try { light = localStorage.getItem("lobster-theme") === "light"; } catch (e) {}
    applyTheme(light);
    $("#btn-theme").onclick = () => applyTheme(!document.body.classList.contains("light"));
  }
  function applyTheme(light) {
    document.body.classList.toggle("light", light);
    $("#btn-theme").textContent = light ? "☀️" : "🌙";
    try { localStorage.setItem("lobster-theme", light ? "light" : "dark"); } catch (e) {}
    if (sceneReady) S.setTheme(light);
  }

  /* ── 視圖切換 ───────────────────────────────────────── */
  function wireViewSwitch() {
    $$("#view-switch button").forEach((b) => {
      b.onclick = () => switchView(b.dataset.view);
    });
  }
  function switchView(v) {
    if (v === currentView) return;
    currentView = v;
    $$("#view-switch button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    closePanel();
    // 先全部隱藏 + 暫停場景
    DG.hide(); if (FLOW) FLOW.hide();
    if (sceneReady) S.setActive(false);
    $("#legend").classList.add("hidden");
    if (v === "scene") {
      ensureScene();
      if (sceneReady) { S.setActive(true); if (pipePaused) S.setFrozen(true); }
      $("#legend").classList.remove("hidden");
    } else if (v === "flow" && FLOW) {
      FLOW.show();
    } else {
      DG.show();
    }
  }

  /* ── demo 面板 ──────────────────────────────────────── */
  function openPanel(id) {
    DEMOS.render(id, $("#panel-content"));
    $("#panel").classList.remove("hidden");
    $("#panel-scrim").classList.remove("hidden");
    $("#tooltip").classList.add("hidden");
    const p = $("#panel"); p.style.animation = "none"; void p.offsetWidth; p.style.animation = "";
  }
  function closePanel() {
    $("#panel").classList.add("hidden");
    $("#panel-scrim").classList.add("hidden");
  }
  function wirePanel() {
    $("#panel-close").onclick = closePanel;
    $("#panel-scrim").onclick = closePanel;
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePanel(); });
  }

  /* ── 場景 hover → tooltip ───────────────────────────── */
  function onSceneHover(id, e) {
    const tip = $("#tooltip");
    if (!id || currentView !== "scene") { tip.classList.add("hidden"); return; }
    const n = L.NODES.find((x) => x.id === id);
    tip.innerHTML = `<div class="tt-title"><span style="color:${n.color}">${n.icon}</span> ${n.label}</div>`
      + `<div class="tt-sub">${n.sub}</div><div class="tt-hint">點擊看實際流程 demo →</div>`;
    tip.style.left = e.clientX + "px"; tip.style.top = e.clientY + "px";
    tip.classList.remove("hidden");
  }

  /* ── 通訊日誌：收合 / 關閉 ──────────────────────────── */
  function wireLog() {
    const sl = $("#statuslog");
    const toggle = () => sl.classList.toggle("collapsed");
    $("#statuslog-head").onclick = (e) => { if (e.target.id !== "statuslog-close") toggle(); };
    $("#statuslog-collapse").onclick = (e) => { e.stopPropagation(); toggle(); };
    $("#statuslog-close").onclick = (e) => { e.stopPropagation(); sl.classList.add("hidden"); };
  }

  /* ── 頂部按鈕 ───────────────────────────────────────── */
  let loopMode = false;
  function toggleLoop() {
    loopMode = !loopMode;
    const b = $("#btn-loop");
    b.classList.toggle("active", loopMode);
    b.innerHTML = loopMode ? '⏹ <span class="btn-full">停止</span>循環' : '🔁 <span class="btn-full">循環</span>';
    if (loopMode && !running) playPipeline();
  }
  function wireToolbar() {
    $("#btn-play").onclick = playPipeline;
    $("#btn-pause").onclick = togglePause;
    $("#btn-loop").onclick = toggleLoop;
    $("#btn-reset").onclick = () => {
      closePanel();
      if (currentView === "scene") { ensureScene(); S.reset(); }
      else if (currentView === "flow") { $("#flow-view").scrollTo({ top: 0, left: 0, behavior: "smooth" }); }
      else { $("#diagram-view").scrollTo({ top: 0, behavior: "smooth" }); $("#diagram-tilt").style.transform = "rotateX(0deg) rotateY(0deg)"; }
    };
  }

  /* =======================================================================
   * 統一 Pipeline 進度動畫（對齊 run_pipeline）
   * 同時驅動：進度步驟器 + 架構圖（高亮 agent / 子步驟 / 資料流）
   *           + 3D 場景（若已建：點亮節點 / 邊）+ 通訊日誌
   * ==================================================================== */
  const AGENT_NAME = { A: "採集者", B: "分析師", C: "預警員", SYS: "系統", LLM: "LLM", DB: "SQLite", EXPORT: "匯出", BOT: "Agent Bot" };
  function log(from, to, msg, cls) {
    const body = $("#statuslog-body");
    const line = document.createElement("div");
    line.className = "log-line " + (cls || "");
    const f = AGENT_NAME[from] || from;
    line.innerHTML = to ? `<span class="log-from">${f}</span> <span class="log-arrow">→ ${AGENT_NAME[to] || to}</span> ${msg}`
      : `<span class="log-sys">${msg}</span>`;
    body.appendChild(line); body.scrollTop = body.scrollHeight;
  }

  // 進度步驟器
  function stepper(activeId) { $$("#pipeline-progress .pp-step").forEach((s) => s.classList.toggle("active", s.dataset.agent === activeId && !s.classList.contains("done"))); }
  function stepperDone(id) { const s = [...$$("#pipeline-progress .pp-step")].find((x) => x.dataset.agent === id); if (s) { s.classList.remove("active"); s.classList.add("done"); } }
  function setSub(html) { $("#pp-sub").innerHTML = html; }
  function setFill(f) { $("#pp-fill").style.width = Math.round(f * 100) + "%"; }
  function resetStepper() { $$("#pipeline-progress .pp-step").forEach((s) => s.classList.remove("active", "done")); setFill(0); setSub("準備中…"); }

  // 安全呼叫 3D 場景（未建時略過）；架構圖已於 boot 建好，可直接呼叫
  const sc = (fn, ...a) => { if (sceneReady) { try { S[fn] && S[fn](...a); } catch (e) {} } };
  // 發射帶訊息的資料封包（只在 3D 場景視圖時 → 看得到流程溝通）
  const pkt = (from, to, opts) => { if (sceneReady && currentView === "scene") { try { S.sendPacket(from, to, opts || {}); } catch (e) {} } };

  let running = false;
  async function playPipeline() {
    if (running) return;
    running = true;
    setPaused(false); // 重置暫停狀態
    const pauseBtn = $("#btn-pause"); if (pauseBtn) { pauseBtn.classList.remove("hidden"); pauseBtn.innerHTML = '⏸ <span class="btn-full">暫停</span>'; pauseBtn.classList.remove("active"); }
    const btn = $("#btn-play"); btn.disabled = true; btn.textContent = "● 執行中…";
    closePanel();
    $("#pipeline-progress").classList.remove("hidden");
    resetStepper();
    $("#statuslog").classList.remove("hidden", "collapsed"); $("#statuslog-body").innerHTML = "";
    DG.resetPipeline(); if (FLOW) FLOW.reset(); // 不強制移動相機 —— 維持使用者目前的視角

    const A = L.DIAGRAM.agents; // [collector, analyst, advisor]
    const totalSteps = A[0].steps.length + A[1].steps.length + A[2].steps.length + 3;
    let done = 0; const bump = () => setFill(++done / totalSteps);

    log("SYS", null, "金鑰就緒，啟動 3-agent Pipeline", "log-sys");
    await sleep(300);

    // ── ① 採集者 ──
    stepper("collector"); DG.highlightAgent("collector"); if (FLOW) FLOW.highlightAgent("collector"); sc("litNode", "collector");
    const colMsg = [
      ["呼叫環境部 EPA aqx_p_432 抓 20 城市測站", "epa", "aqx_p_432"],
      ["並行拉取 民生公共物聯網 + LASS-net Airbox", "civic", "PM2.5 感測"],
      ["合併 Open-Meteo 氣象 + CAMS 大氣化學模式", "openmeteo", "氣象 + CAMS"],
      ["清洗去重：原始 1287 → 保留 1043（保留率 81.0%）", null, null],
    ];
    for (let i = 0; i < A[0].steps.length; i++) {
      DG.stepState("collector", i, "active");
      setSub(`<span class="hl">① 採集者</span> ▸ ${A[0].steps[i].name}`);
      log("A", "SYS", colMsg[i][0]);
      if (colMsg[i][1]) { DG.boostFlow("src-" + colMsg[i][1], "pipeline-band", true); pkt(colMsg[i][1], "collector", { label: colMsg[i][2] }); }
      await sleep(620);
      if (colMsg[i][1]) DG.boostFlow("src-" + colMsg[i][1], "pipeline-band", false);
      DG.stepState("collector", i, "done"); bump();
    }
    stepperDone("collector");
    DG.boostFlow("blk-app", "agent-collector", true);
    pkt("collector", "analyst", { label: "資料封包 · 20 城市", big: true });
    log("A", "B", "資料封包完成 → 20 城市 + 1043 筆民間感測 + 24h 歷史");
    await sleep(450);

    // ── ② 分析師 ──
    stepper("analyst"); DG.highlightAgent("analyst"); if (FLOW) FLOW.highlightAgent("analyst"); sc("litNode", "analyst");
    const anMsg = [
      "加權公式 0.40·PM2.5 + 0.20·AQI + 0.15·O3 …",
      "偵測 24h 趨勢與日夜雙峰",
      "RAG 檢索：WHO 2021、EPA NAAQS、Lancet 2023",
      "推估未來 6 小時走勢",
    ];
    for (let i = 0; i < A[1].steps.length; i++) {
      DG.stepState("analyst", i, "active");
      setSub(`<span class="hl">② 分析師</span> ▸ ${A[1].steps[i].name}`);
      log("B", "SYS", anMsg[i]);
      if (i === 2) { DG.boostFlow("agent-analyst", "svc-llm", true); pkt("rag", "analyst", { label: "文獻片段" }); }
      await sleep(620);
      DG.stepState("analyst", i, "done"); bump();
    }
    pkt("analyst", "llm", { label: "風險 prompt" });
    log("B", "LLM", "請 LLM 生成 3 段風險分析報告", "log-llm"); await sleep(500);
    pkt("llm", "analyst", { label: "3 段報告" });
    log("LLM", "B", "分析完成（現況 / 健康建議 / 未來 6h）", "log-ok");
    DG.boostFlow("agent-analyst", "svc-llm", false);
    stepperDone("analyst");
    pkt("analyst", "advisor", { label: "風險分級", big: true });
    log("B", "C", "報告寫好了，轉交預警員生成健康建議"); await sleep(450);

    // ── ③ 預警員 ──
    stepper("advisor"); DG.highlightAgent("advisor"); if (FLOW) FLOW.highlightAgent("advisor"); sc("litNode", "advisor");
    DG.boostFlow("agent-advisor", "svc-llm", true); pkt("advisor", "llm", { label: "個人化 prompt" });
    const grp = A[2].steps;
    for (let i = 0; i < grp.length; i++) {
      DG.stepState("advisor", i, "active");
      setSub(`<span class="hl">③ 預警員</span> ▸ ${grp[i].name}`);
      log("C", "SYS", `${grp[i].name}：依個人檔案(年齡 / 診斷 / 閾值)計算`);
      await sleep(430);
      DG.stepState("advisor", i, "done"); bump();
    }
    pkt("llm", "advisor", { label: "個人化建議" });
    DG.boostFlow("agent-advisor", "svc-llm", false);
    log("LLM", "C", "個人化建議生成完成（20 城市）", "log-ok"); await sleep(300);

    // ── 輸出：SQLite + 匯出 JSON → Agent Bot 拉取 ──
    if (FLOW) FLOW.highlightAgent("output");
    setSub(`<span class="hl">輸出</span> ▸ 寫入 SQLite 時序快取`);
    DG.boostFlow("pipeline-band", "blk-storage", true); pkt("advisor", "sqlite", { label: "寫入快照", color: L.C.green });
    log("C", "DB", "寫入本機 SQLite 時序快取（20 城市）"); await sleep(400); bump();
    pkt("advisor", "export", { label: "匯出 JSON", color: L.C.green });
    log("C", "EXPORT", "已匯出 hermes_export/latest_aqi.json（Agent Bot 可拉取）", "log-ok"); await sleep(400); bump();
    DG.boostFlow("pipeline-band", "blk-storage", false);

    setSub(`<span class="hl">Agent Bot</span> ▸ 讀 JSON 在聊天平台回答`);
    DG.boostFlow("blk-storage", "svc-hermes", true);
    pkt("export", "hermes", { label: "拉取", color: L.C.purple }); await sleep(250);
    pkt("hermes", "discord", { label: "回答", color: L.C.cyan });
    log("C", "BOT", "Agent Bot 讀 latest_aqi.json → 在聊天平台回答（含 persona）", "log-ok"); await sleep(450); bump();
    DG.boostFlow("blk-storage", "svc-hermes", false);

    stepperDone("advisor"); setFill(1);
    setSub('<span class="hl">✓ Pipeline 完成</span> · 所有代理人下線');
    log("SYS", null, "✓ Pipeline 完成 · 所有代理人下線", "log-ok");
    // 完成後不重置相機 —— 維持使用者視角

    btn.disabled = false; btn.textContent = "▶ 跑一次 Pipeline";
    running = false; setPaused(false);
    const pb = $("#btn-pause"); if (pb) pb.classList.add("hidden");
    if (loopMode) {
      // 循環模式：稍候自動再跑一次（進度條保持顯示）
      setTimeout(() => { if (loopMode && !running) playPipeline(); }, 1600);
    } else {
      setTimeout(() => { if (!running && !loopMode) $("#pipeline-progress").classList.add("hidden"); DG.resetPipeline(); if (FLOW) FLOW.reset(); }, 3500);
    }
  }

  global.LOBSTER_MAIN = { playPipeline, openPanel, switchView };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})(window);
