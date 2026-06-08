/* =============================================================================
 * demos.js — 每個節點點開後的「真實流程 demo」
 * 採集者 / 分析師 / 預警員 / RAG 為可互動動畫，其餘為對齊原始碼的資訊卡。
 * 對外：LOBSTER_DEMOS.render(nodeId, containerEl)
 * ========================================================================== */
(function (global) {
  "use strict";
  const L = global.LOBSTER;

  /* ── 小工具 ─────────────────────────────────────────── */
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const el = (html) => { const d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; };
  const mean = (a) => a.reduce((s, x) => s + x, 0) / a.length;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const scene = () => global.LOBSTER_SCENE;
  // 開啟互動 demo 時自動跑一次（使用者仍可按按鈕重跑）
  const autorun = (c) => setTimeout(() => { const b = c.querySelector("#d-run"); if (b && document.body.contains(b)) b.click(); }, 480);

  function animateCount(node, from, to, dur, fmt) {
    const t0 = performance.now();
    fmt = fmt || ((v) => Math.round(v));
    (function step(now) {
      const k = Math.min(1, (now - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3);
      node.textContent = fmt(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step);
    })(t0);
  }
  function typeInto(node, text, cps, done) {
    node.innerHTML = ""; let i = 0;
    const cur = el('<span class="cursor"></span>'); node.appendChild(cur);
    const iv = setInterval(() => {
      if (i >= text.length) { clearInterval(iv); cur.remove(); if (done) done(); return; }
      cur.insertAdjacentText("beforebegin", text[i++]);
      node.scrollTop = node.scrollHeight;
    }, 1000 / cps);
  }

  /* ── 標頭 ───────────────────────────────────────────── */
  function header(node, eyebrow, tags) {
    return `
      <div class="p-eyebrow" style="color:${node.color}">${esc(eyebrow)}</div>
      <div class="p-title">${node.icon} ${esc(node.label)}</div>
      <div class="p-sub">${esc(node.sub)}</div>
      <div class="p-tags">${tags.map((t) => `<span class="p-tag">${esc(t)}</span>`).join("")}</div>`;
  }
  const sh = (color, txt) => `<div class="p-section-h" style="color:${color}">${esc(txt)}</div>`;

  /* =======================================================================
   * 各節點 demo body
   * ==================================================================== */
  const BODY = {

    /* ── 使用者瀏覽器 ─────────────────────────────────── */
    user(node, c) {
      c.innerHTML = `
        ${sh(node.color, "封面 → 一鍵啟動")}
        <div class="card" style="padding:0;overflow:hidden">
          <div style="display:flex;gap:6px;padding:9px 12px;border-bottom:1px solid var(--line);background:#0a0e1c">
            <span style="width:10px;height:10px;border-radius:50%;background:#ff4757"></span>
            <span style="width:10px;height:10px;border-radius:50%;background:#ffd93d"></span>
            <span style="width:10px;height:10px;border-radius:50%;background:#00e676"></span>
            <span style="margin-left:8px;font-family:var(--mono);font-size:0.7rem;color:var(--muted)">localhost:8501</span>
          </div>
          <div style="padding:26px 18px;text-align:center;background:radial-gradient(circle at 50% 0%,#0d1430,#070a16)">
            <div style="font-size:2.4rem;filter:drop-shadow(0 0 16px var(--cyan))">🦞</div>
            <div style="font-size:1.4rem;font-weight:900;margin:6px 0">LobsterAQI</div>
            <div style="color:var(--muted);font-size:0.78rem;margin-bottom:16px">由分析師整合 RAG 文獻，預警員依個人檔案給個人化建議</div>
            <button class="btn-demo" id="d-launch" style="background:linear-gradient(135deg,#007a99,#00d9ff);border-color:#00d9ff;color:#02121a">▶ 啟動三代理人 Pipeline</button>
          </div>
        </div>
        ${sh(node.color, "使用者旅程")}
        <div class="flow-steps">
          <div class="flow-step">Sidebar 填 <b>LLM 金鑰</b>（Claude / Gemini / …）+ <b>EPA Open Data Token</b></div>
          <div class="flow-step">封面按「▶ 啟動三代理人 Pipeline」</div>
          <div class="flow-step">smooth scroll 到劇場區，3 個 agent 依序亮起跑分析（~10–30 秒）</div>
          <div class="flow-step">主儀表板出來：02–10 共 9 個資料 SECTION 解鎖</div>
          <div class="flow-step">右下角浮動 AI 助理隨時問空品；點城市開深入 modal</div>
        </div>
        <p class="p-desc muted">所有資料 section 都 gate 在「啟動」之後 — 第一次進入只有 hero 與一鍵啟動。</p>`;
      c.querySelector("#d-launch").onclick = () => global.LOBSTER_MAIN && global.LOBSTER_MAIN.playPipeline();
    },

    /* ── LobsterAQI Streamlit ─────────────────────────── */
    app(node, c) {
      c.innerHTML = `
        <p class="p-desc">LobsterAQI 是 <b>Streamlit 單頁應用</b> — 從封面捲到底，依序 10 個 SECTION。主儀表板上方有<b>時間軸 scrubber</b>，可看過去 24h 任一時點快照；點城市開<b>深入 modal</b>（不換頁、捲動位置保留）。</p>
        ${sh(node.color, "單頁 10 個 SECTION")}
        <div class="sec-list">
          ${L.SECTIONS.map((s) => `
            <div class="sec-item">
              <span class="sec-no">${s.no}</span>
              <span class="sec-ic">${s.icon}</span>
              <div class="sec-body"><div class="nm">${esc(s.name)}</div><div class="ds">${esc(s.desc)}</div></div>
            </div>`).join("")}
        </div>
        ${sh(node.color, "技術堆疊")}
        <div class="card">
          <div class="card-row"><span class="k">前端框架</span><span class="v">Streamlit（Python 單頁）</span></div>
          <div class="card-row"><span class="k">圖表</span><span class="v">Plotly（charts.py 工廠）</span></div>
          <div class="card-row"><span class="k">狀態</span><span class="v">st.session_state</span></div>
          <div class="card-row"><span class="k">自動更新</span><span class="v">st.fragment(run_every=60s)</span></div>
          <div class="card-row"><span class="k">主題</span><span class="v">深色 CSS（styles.py）</span></div>
        </div>`;
    },

    /* ── 採集者 A（互動 ETL）──────────────────────────── */
    collector(node, c) {
      c.innerHTML = `
        <p class="p-desc"><b>純 ETL，無 LLM</b>。並行拉三個資料源、清洗去重，組成 20 城市資料封包交給分析師。早期 5-agent 設計的「爬蟲員」已併入此處。</p>
        <button class="btn-demo" id="d-run">▶ 執行採集流程</button>
        ${sh(node.color, "① 環境部 EPA aqx_p_432 · 20 城市")}
        <div class="city-grid" id="d-cities"></div>
        ${sh(node.color, "② 民間感測器並行清洗（CleaningReport）")}
        <div class="clean-stats">
          <div class="clean-stat"><div class="num" id="cs-raw" style="color:var(--muted)">—</div><div class="lbl">原始筆數</div></div>
          <div class="clean-stat"><div class="num" id="cs-keep" style="color:var(--green)">—</div><div class="lbl">保留</div></div>
          <div class="clean-stat"><div class="num" id="cs-drop" style="color:var(--orange)">—</div><div class="lbl">丟棄</div></div>
        </div>
        <div class="card" id="d-reasons" style="display:none">
          <div class="card-row"><span class="k">超出地理範圍</span><span class="v" id="r1">0</span></div>
          <div class="card-row"><span class="k">數值異常 / 超量程</span><span class="v" id="r2">0</span></div>
          <div class="card-row"><span class="k">缺必要欄位</span><span class="v" id="r3">0</span></div>
          <div class="card-row"><span class="k">重複測站去重</span><span class="v" id="r4">0</span></div>
        </div>
        ${sh(node.color, "③ 資料封包 → 分析師")}
        <div class="llm-out" id="d-packet" style="border-left-color:var(--cyan);min-height:auto">點上方按鈕開始…</div>`;

      const grid = c.querySelector("#d-cities");
      const snap = L.snapshot();
      grid.innerHTML = snap.map((r) => `
        <div class="city-cell"><div class="cn">${esc(r.city)}</div><div class="ca" style="color:${r.level.color}">${r.aqi}</div></div>`).join("");

      c.querySelector("#d-run").onclick = async (e) => {
        const btn = e.target; btn.disabled = true; btn.textContent = "採集中…";
        scene() && (scene().litNode("collector"), scene().boostEdge("epa", "collector"), scene().boostEdge("civic", "collector"), scene().boostEdge("openmeteo", "collector"));
        const cells = grid.querySelectorAll(".city-cell");
        cells.forEach((x) => x.classList.remove("show"));
        for (let i = 0; i < cells.length; i++) { cells[i].classList.add("show"); await sleep(45); }
        // 清洗
        const raw = 1287, drop = 244, keep = raw - drop;
        animateCount(c.querySelector("#cs-raw"), 0, raw, 700);
        await sleep(350);
        animateCount(c.querySelector("#cs-keep"), 0, keep, 800);
        animateCount(c.querySelector("#cs-drop"), 0, drop, 800);
        await sleep(500);
        c.querySelector("#d-reasons").style.display = "block";
        animateCount(c.querySelector("#r1"), 0, 96, 500);
        animateCount(c.querySelector("#r2"), 0, 71, 500);
        animateCount(c.querySelector("#r3"), 0, 48, 500);
        animateCount(c.querySelector("#r4"), 0, 29, 500);
        await sleep(500);
        scene() && scene().boostEdge("collector", "analyst");
        const cov = 17;
        typeInto(c.querySelector("#d-packet"),
          `✓ 保留率 ${(keep/raw*100).toFixed(1)}%（離島放寬到 20 km 半徑）\n`
          + `✓ 對應 ${cov}/20 城市有民間感測站覆蓋\n`
          + `→ 傳送 20 城市官方資料 + ${keep} 筆民間感測 + 24h 歷史 → 分析師`, 55);
        btn.disabled = false; btn.textContent = "▶ 重新執行";
      };
      autorun(c);
    },

    /* ── 分析師 B（互動：公式 + RAG + LLM）────────────── */
    analyst(node, c) {
      c.innerHTML = `
        <p class="p-desc">pipeline 中 <b>LLM 負擔最重</b>的一隻。收資料後綜合分析 + 引用 RAG 文獻，產出 3 段風險報告。右下角 AI 助理也走它。</p>
        <button class="btn-demo" id="d-run">▶ 生成風險分析</button>
        ${sh(node.color, "① 加權風險公式")}
        <div id="d-formula"></div>
        ${sh(node.color, "② RAG 文獻檢索（top-k）")}
        <div id="d-rag"></div>
        ${sh(node.color, "③ LLM 生成 3 段報告")}
        <div class="llm-out" id="d-report">等待生成…</div>`;

      // 公式條
      const fdiv = c.querySelector("#d-formula");
      fdiv.innerHTML = L.RISK_FORMULA.map((f) => `
        <div class="bar-row"><span class="bl">${esc(f.k)}</span>
          <div class="bar-track"><div class="bar-fill" data-w="${f.w}" style="background:linear-gradient(90deg,#6c3fd6,#9b59ff)"></div></div>
          <span class="bv">${(f.w*100).toFixed(0)}%</span></div>`).join("");

      // RAG chips
      const rdiv = c.querySelector("#d-rag");
      rdiv.innerHTML = L.RAG_SNIPPETS.map((s, i) => `
        <div class="rag-chip" data-i="${i}">
          <span class="score">—</span>
          <div><div class="src">${esc(s.source)}</div><div class="qt">${esc(s.quote)}</div></div>
        </div>`).join("");

      c.querySelector("#d-run").onclick = async (e) => {
        const btn = e.target; btn.disabled = true; btn.textContent = "分析中…";
        scene() && (scene().litNode("analyst"), scene().boostEdge("rag", "analyst"), scene().boostEdge("llm", "analyst"));
        // 公式條動畫
        fdiv.querySelectorAll(".bar-fill").forEach((b) => b.style.width = "0");
        await sleep(50);
        fdiv.querySelectorAll(".bar-fill").forEach((b) => b.style.width = (b.dataset.w * 100 * 2.5) + "%");
        await sleep(900);
        // RAG 命中
        const scores = [0.82, 0.74, 0.91, 0.68];
        const chips = rdiv.querySelectorAll(".rag-chip");
        for (let i = 0; i < chips.length; i++) {
          chips[i].querySelector(".score").textContent = scores[i].toFixed(2);
          if (scores[i] >= 0.74) chips[i].classList.add("hit");
          await sleep(220);
        }
        await sleep(300);
        // 生成報告（引用即時快照數值）
        const snap = L.snapshot();
        const worst = snap[0], best = snap[snap.length - 1];
        const avg = mean(snap.map((r) => r.aqi));
        const report =
`① 現況摘要
全國平均 AQI ${avg.toFixed(1)}，整體為「${L.aqiToLevel(avg).name}」等級。最高為 ${worst.city} AQI ${worst.aqi}（${worst.level.name}，PM2.5 ${worst["PM2.5"]} μg/m³），最低為 ${best.city} AQI ${best.aqi}。

② 健康建議
${worst.city} PM2.5 已達 ${worst["PM2.5"]} μg/m³，超過 WHO 2021 的 24h 15 μg/m³ 標準。氣喘、心血管與年長族群應減少該區戶外活動；依 Lancet 2023，AQI > 100 時劇烈運動肺部沉積量提升 3–5 倍，建議改室內。

③ 未來 6 小時研判
依日夜雙峰（早 8、晚 6 通勤尖峰），${worst.city}、台中、高雄一帶傍晚 PM2.5 可能再升一級；東部與離島（台東、澎湖）維持良好，適合戶外。`;
        typeInto(c.querySelector("#d-report"), report, 90, () => {
          scene() && scene().boostEdge("analyst", "advisor");
        });
        btn.disabled = false; btn.textContent = "▶ 重新生成";
      };
      autorun(c);
    },

    /* ── 預警員 C（互動：5 族群卡）────────────────────── */
    advisor(node, c) {
      const snap = L.snapshot();
      c.innerHTML = `
        <p class="p-desc">Pipeline 倒數第二步。<b>針對「你這個人」</b>(不再分五大族群)依個人健康檔案(年齡 / BMI / 已診斷疾病 / 你的 AQI 閾值)產出建議。只在使用者有填個人檔案時才呼叫 LLM(省 token);沒填則 UI 顯示 CTA banner。</p>
        ${sh(node.color, "個人化 safe_hours 公式")}
        <div class="codebox"><span class="cm"># app.py SECTION · 08(以你的閾值為門檻)</span>
safe_hours = <span class="ck">max</span>(0, 12 - <span class="ck">max</span>(0, AQI - <span class="cn">你的閾值</span>) × 0.15)</div>
        ${sh(node.color, "選城市 + 設你的閾值,即時試算")}
        <select id="d-city" class="btn" style="width:100%;margin:4px 0 2px">
          ${snap.map((r) => `<option value="${r.aqi}">${esc(r.city)} · AQI ${r.aqi}（${r.level.name}）</option>`).join("")}
        </select>
        <div style="margin:10px 0 2px">
          <div style="display:flex;justify-content:space-between;font-size:0.76rem;color:var(--muted);margin-bottom:4px">
            <span>情境 AQI</span><span class="v" id="d-aqi-val" style="color:var(--green)">${snap[0].aqi}</span>
          </div>
          <input type="range" id="d-aqi" min="20" max="220" value="${snap[0].aqi}" style="width:100%;accent-color:var(--green)" />
          <div style="display:flex;justify-content:space-between;font-size:0.76rem;color:var(--muted);margin:9px 0 4px">
            <span>你的 AQI 閾值(個人化)</span><span class="v" id="d-thr-val" style="color:var(--cyan)">100</span>
          </div>
          <input type="range" id="d-thr" min="20" max="200" value="100" style="width:100%;accent-color:var(--cyan)" />
        </div>
        <div class="card" id="d-personal" style="margin-top:10px;border-left:3px solid var(--green)">
          <div class="card-row"><span class="k">今日建議戶外</span><span class="v hours" style="color:var(--green)">— h</span></div>
          <div class="adv" style="margin-top:6px;font-size:0.82rem;color:var(--muted)">拉滑桿即時試算</div>
        </div>`;

      function maskAdvice(h) {
        if (h >= 8) return { t: "✓ 正常活動，免戴口罩", col: "var(--green)" };
        if (h >= 4) return { t: "🧣 一般外科口罩即可", col: "var(--yellow)" };
        if (h > 0)  return { t: "😷 建議 N95，縮短戶外時間", col: "var(--orange)" };
        return { t: "🚫 以室內為主，關窗開清淨機", col: "var(--red)" };
      }
      const slider = c.querySelector("#d-aqi"), aqiVal = c.querySelector("#d-aqi-val");
      const thr = c.querySelector("#d-thr"), thrVal = c.querySelector("#d-thr-val");
      const card = c.querySelector("#d-personal");
      function recompute() {
        const aqi = +slider.value, limit = +thr.value;
        const h = Math.max(0, 12 - Math.max(0, aqi - limit) * 0.15);
        const m = maskAdvice(h);
        card.querySelector(".hours").textContent = h.toFixed(1) + " h";
        card.querySelector(".hours").style.color = m.col;
        card.querySelector(".adv").textContent = `安全戶外 ${h.toFixed(1)} 小時 · ${m.t}`;
        card.style.borderLeftColor = m.col;
        scene() && (scene().litNode("advisor"), scene().boostEdge("llm", "advisor"), scene().boostEdge("advisor", "export"));
      }
      c.querySelector("#d-city").onchange = (ev) => { slider.value = ev.target.value; aqiVal.textContent = ev.target.value; recompute(); };
      slider.oninput = () => { aqiVal.textContent = slider.value; recompute(); };
      thr.oninput = () => { thrVal.textContent = thr.value; recompute(); };
      recompute();
    },

    /* ── 環境部 EPA ───────────────────────────────────── */
    epa(node, c) {
      c.innerHTML = `
        <p class="p-desc">台灣官方即時空品來源。需要你自己的 <b>EPA Open Data Token</b>（環境部資料開放平臺申請）。</p>
        ${sh(node.color, "兩個端點")}
        <div class="card">
          <div class="card-row"><span class="k">即時 AQI</span><span class="v">aqx_p_432</span></div>
          <div class="card-row"><span class="k">24h 歷史</span><span class="v">aqx_p_488</span></div>
          <div class="card-row"><span class="k">主機</span><span class="v">data.moenv.gov.tw</span></div>
          <div class="card-row"><span class="k">金鑰</span><span class="v" style="color:var(--orange)">✓ 必填 api_key</span></div>
        </div>
        ${sh(node.color, "回應樣本（aqx_p_432）")}
        <div class="codebox">{
  <span class="ck">"records"</span>: [
    {
      <span class="ck">"sitename"</span>: <span class="cs">"前金"</span>,
      <span class="ck">"county"</span>:   <span class="cs">"高雄市"</span>,
      <span class="ck">"aqi"</span>:      <span class="cs">"86"</span>,
      <span class="ck">"pm2.5"</span>:    <span class="cs">"38"</span>,
      <span class="ck">"status"</span>:   <span class="cs">"普通"</span>,
      <span class="ck">"publishtime"</span>: <span class="cs">"2026/06/07 13:00"</span>
    }, …
  ]
}</div>
        <p class="p-desc muted">採集者用 <b>_resolve_col</b> 容錯解析欄位 — MOENV 偶爾改 schema（大小寫 / 全形），這層讓欄位對應不死。20+ 測站依縣市聚合成 20 城市單值。</p>`;
    },

    /* ── Open-Meteo / CAMS ────────────────────────────── */
    openmeteo(node, c) {
      c.innerHTML = `
        <p class="p-desc">兩個<b>免金鑰</b>的公開端點：氣象 + 大氣化學模式（Copernicus CAMS）。提供溫濕度、風向氣壓，以及 24h 歷史 + 模式預測。</p>
        ${sh(node.color, "端點")}
        <div class="card">
          <div class="card-row"><span class="k">氣象</span><span class="v">api.open-meteo.com/v1/forecast</span></div>
          <div class="card-row"><span class="k">空品模式</span><span class="v">air-quality-api…/v1/air-quality</span></div>
          <div class="card-row"><span class="k">金鑰</span><span class="v" style="color:var(--green)">✗ 公開免金鑰</span></div>
        </div>
        ${sh(node.color, "關鍵參數技巧")}
        <div class="codebox"><span class="cm"># app.py run_pipeline</span>
fetch_open_meteo_aq_batch(CITIES,
    past_days=<span class="cn">7</span>,       <span class="cm"># 一週進 SQLite 供「本週 vs 上週」</span>
    forecast_days=<span class="cn">1</span>)   <span class="cm"># 把「今天」拉進來，否則落後 10+ 小時</span>

<span class="cm"># 砍掉 now 之後的預測段，只留實測</span>
df = df[df.timestamp &lt;= now]</div>
        <p class="p-desc muted">CAMS 是「永遠在線」的搭檔：即使 EPA 歷史因缺金鑰失敗，熱力圖的 CAMS 分頁照樣能畫。</p>`;
    },

    /* ── 民間感測器 ───────────────────────────────────── */
    civic(node, c) {
      c.innerHTML = `
        <p class="p-desc">兩個<b>公開</b>民間 PM2.5 即時來源，補官方測站涵蓋不到的角落（尤其離島）。</p>
        ${sh(node.color, "兩個來源")}
        <div class="card">
          <div class="card-row"><span class="k">主要</span><span class="v">民生公共物聯網</span></div>
          <div class="card-row"><span class="k">API</span><span class="v">sta.colife.org.tw（SensorThings）</span></div>
          <div class="card-row"><span class="k">補充</span><span class="v">LASS-net Airbox</span></div>
          <div class="card-row"><span class="k">API</span><span class="v">pm25.lass-net.org</span></div>
        </div>
        ${sh(node.color, "清洗管線（CleaningReport）")}
        <div class="flow-steps">
          <div class="flow-step">並行 GET 兩個 API，合併原始測點</div>
          <div class="flow-step">過濾超出台灣地理範圍 / 超量程 / 缺欄位的點</div>
          <div class="flow-step">同位置重複測站去重</div>
          <div class="flow-step">對應到 20 城市（離島放寬 <b>20 km</b> 半徑）</div>
          <div class="flow-step">產出 raw / kept / dropped + 丟棄原因統計</div>
        </div>
        <p class="p-desc muted">輸出餵給 SECTION · 06「官方 vs 民間」做測站對比；失敗時 pipeline 照常跑（只略過該對比）。</p>`;
    },

    /* ── RAG 知識庫（向量空間最近鄰檢索視覺化）──────────── */
    rag(node, c) {
      const COL = L.C;
      // 知識庫文件 chunk（4 份真實 snippet + 示意 chunk）+ 在 2D 語意空間的投影座標
      const CORPUS = [
        { src: "WHO 2021",      txt: "PM2.5 年均 ≤ 5、24h ≤ 15 μg/m³",   x: 0.17, y: 0.26, c: COL.cyan },
        { src: "US EPA NAAQS",  txt: "PM2.5 24h ≤ 35、年均 ≤ 12 μg/m³",  x: 0.30, y: 0.15, c: COL.cyan },
        { src: "台灣 AQI 手冊", txt: "AQI 六級分級標準（0-500）",         x: 0.13, y: 0.41, c: COL.cyan },
        { src: "Lancet 2023",   txt: "高 PM2.5 劇烈運動，肺沉積 ↑3-5x",   x: 0.81, y: 0.21, c: COL.orange },
        { src: "運動生理學",    txt: "戶外運動換氣量↑，吸入污染量↑",     x: 0.88, y: 0.35, c: COL.orange },
        { src: "孕婦暴露研究",  txt: "孕期 PM2.5 與早產、低出生體重相關", x: 0.40, y: 0.81, c: COL.green },
        { src: "兒童呼吸道",    txt: "兒童呼吸道發育中，對 PM2.5 更敏感", x: 0.55, y: 0.87, c: COL.green },
        { src: "心血管事件",    txt: "急性 PM2.5 暴露 ↑ 心梗、中風風險",  x: 0.69, y: 0.73, c: COL.red },
        { src: "[個人病歷]",    txt: "氣喘 J45 · 肺功能 FEV1 72%",        x: 0.50, y: 0.53, c: COL.purple, personal: true },
      ];
      const PRESETS = ["氣喘 運動 戶外 風險", "孕婦 PM2.5 影響", "口罩 標準 限值濃度", "心血管 急性 暴露"];

      c.innerHTML = `
        <p class="p-desc">RAG 把<b>查詢</b>與知識庫<b>文件</b>都轉成向量，在向量空間找<b>最近鄰</b>（語意最相近）的片段餵給 LLM。下圖是知識庫在 2D 語意投影的向量空間：</p>
        ${sh(node.color, "向量空間 · 最近鄰檢索")}
        <div class="vec-wrap"><canvas id="vec-canvas"></canvas>
          <span class="vec-ax vec-ax-x">語意維度 1 →</span><span class="vec-ax vec-ax-y">語意維度 2 ↑</span>
        </div>
        <div class="vec-presets" id="vec-presets">${PRESETS.map((p) => `<span class="vec-chip">${esc(p)}</span>`).join("")}</div>
        <input id="d-q" class="btn" style="width:100%;margin:6px 0" value="${esc(PRESETS[0])}" />
        <button class="btn-demo" id="d-run" style="width:100%">🔍 嵌入查詢 → 檢索最近鄰 (k=3)</button>
        ${sh(node.color, "查詢向量（1536-d → 投影示意）")}
        <div class="vec-embed" id="vec-embed"></div>
        ${sh(node.color, "Top-k 命中 · cosine 相似度")}
        <div id="d-hits"></div>
        ${sh(node.color, "檢索演算法")}
        <div class="codebox"><span class="cm"># 內建輕量版：2-char n-gram 字元重疊（零依賴）</span>
sim(q, chunk) = overlap(q, chunk) × (1.4 <span class="ck">if</span> personal <span class="ck">else</span> 1.0)
top_k = nearest_neighbors(q, chunks, k=5)
<span class="cm"># 進階版：改用真實 embedding + 向量索引（見 hermes_skills / openclaw_skills）</span></div>
        <p class="p-desc muted">預設 4 份文獻 + 使用者上傳 PDF/TXT/MD（pdfplumber 抽取）；個人病歷 scope 享 <b>1.4× 加權</b>，所以更容易被命中。</p>`;

      const cv = c.querySelector("#vec-canvas");
      const ctx = cv.getContext("2d");
      const hits = c.querySelector("#d-hits");
      const embedEl = c.querySelector("#vec-embed");
      let W = 0, H = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);
      function size() {
        W = cv.clientWidth || 480; H = 300;
        cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + "px";
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      const PAD = 30;
      const px = (x) => PAD + x * (W - 2 * PAD);
      const py = (y) => PAD + y * (H - 2 * PAD);

      function ngramSim(q, text) {
        let hit = 0; const seen = new Set();
        for (let i = 0; i < q.length - 1; i++) { const g = q.substr(i, 2).trim(); if (g.length === 2 && !seen.has(g) && text.includes(g)) { hit++; seen.add(g); } }
        return Math.min(0.97, 0.1 + hit * 0.15);
      }
      function hash(s) { let h = 2166136261 >>> 0; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }

      let state = { q: null, t: 1 };
      function search(q) {
        scene() && (scene().litNode("rag"), scene().sendPacket && scene().sendPacket("rag", "analyst", { label: "文獻片段" }));
        const ranked = CORPUS.map((d, i) => {
          let s = ngramSim(q, d.src + d.txt);
          if (d.personal) s = Math.min(0.98, s * 1.4);
          return { d, i, sim: s };
        }).sort((a, b) => b.sim - a.sim);
        // 查詢落點：top-3 依相似度加權的質心
        const top = ranked.slice(0, 3);
        let qx = 0, qy = 0, w = 0;
        top.forEach((r) => { qx += r.d.x * (r.sim + 0.05); qy += r.d.y * (r.sim + 0.05); w += r.sim + 0.05; });
        qx = w ? qx / w : 0.5; qy = w ? qy / w : 0.5;
        const retr = new Set(top.map((r) => r.i));
        state = { q: { x: qx, y: qy, text: q }, ranked, retr, t: 0 };
        // 查詢向量條
        let h = hash(q); const cells = [];
        for (let i = 0; i < 18; i++) { h = Math.imul(h ^ (h >>> 13), 16777619) >>> 0; cells.push(h % 100 / 100); }
        embedEl.innerHTML = `<span class="vec-lab">[</span>` + cells.map((v) => `<span class="vec-cell" style="opacity:${(0.25 + v * 0.75).toFixed(2)};background:${COL.purple}"></span>`).join("") + `<span class="vec-lab">…]</span>`;
        // 命中清單
        hits.innerHTML = ranked.map((r, rank) => `
          <div class="rag-chip ${retr.has(r.i) ? "hit" : ""}">
            <span class="score" style="color:${r.d.c}">${r.sim.toFixed(2)}</span>
            <div><div class="src">${rank < 3 ? "✓ " : ""}${esc(r.d.src)}${r.d.personal ? ' <span class="pill-inline" style="background:rgba(155,89,255,.2);color:#c9a6ff">×1.4</span>' : ""}</div><div class="qt">${esc(r.d.txt)}</div></div>
          </div>`).join("");
      }

      function draw() {
        ctx.clearRect(0, 0, W, H);
        // 網格
        ctx.strokeStyle = "rgba(120,140,180,0.08)"; ctx.lineWidth = 1;
        for (let i = 1; i < 8; i++) { const gx = PAD + i / 8 * (W - 2 * PAD); ctx.beginPath(); ctx.moveTo(gx, PAD); ctx.lineTo(gx, H - PAD); ctx.stroke(); }
        for (let i = 1; i < 5; i++) { const gy = PAD + i / 5 * (H - 2 * PAD); ctx.beginPath(); ctx.moveTo(PAD, gy); ctx.lineTo(W - PAD, gy); ctx.stroke(); }

        const S = state, t = S.t, now = performance.now() / 1000;
        // 連線
        if (S.q) {
          const QX = px(S.q.x), QY = py(S.q.y);
          S.ranked.forEach((r) => {
            const DX = px(r.d.x), DY = py(r.d.y);
            const isHit = S.retr.has(r.i);
            const a = (isHit ? Math.min(0.95, 0.55 + r.sim * 0.5) : (0.1 + r.sim * 0.18)) * t;
            ctx.strokeStyle = hexA2(r.d.c, a); ctx.lineWidth = isHit ? 2 + r.sim * 2.5 : 1;
            if (isHit) { ctx.shadowColor = r.d.c; ctx.shadowBlur = 9; }
            ctx.beginPath(); ctx.moveTo(QX, QY);
            ctx.lineTo(QX + (DX - QX) * t, QY + (DY - QY) * t); ctx.stroke();
            ctx.shadowBlur = 0;
            if (isHit && t > 0.5) { // 相似度標籤
              const mx = QX + (DX - QX) * 0.55, my = QY + (DY - QY) * 0.55;
              ctx.fillStyle = hexA2(r.d.c, (t - 0.5) * 2); ctx.font = "700 11px JetBrains Mono, monospace"; ctx.textAlign = "center";
              ctx.fillText(r.sim.toFixed(2), mx, my - 3);
            }
          });
          // kNN 虛線圈
          let rad = 0; S.ranked.forEach((r) => { if (S.retr.has(r.i)) rad = Math.max(rad, Math.hypot(px(r.d.x) - QX, py(r.d.y) - QY)); });
          ctx.setLineDash([4, 4]); ctx.strokeStyle = hexA2("#9b59ff", 0.4 * t); ctx.lineWidth = 1;
          ctx.beginPath(); ctx.arc(QX, QY, (rad + 16) * t, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
        }
        // 文件點
        CORPUS.forEach((d, i) => {
          const X = px(d.x), Y = py(d.y);
          const isHit = S.q && S.retr.has(i);
          const pulse = 1 + Math.sin(now * 2 + i) * 0.12;
          const r = (isHit ? 7 : 4.5) * (isHit ? pulse : 1);
          if (isHit) { ctx.fillStyle = hexA2(d.c, 0.25 * t); ctx.beginPath(); ctx.arc(X, Y, r + 8 * t, 0, 6.28); ctx.fill(); }
          ctx.fillStyle = d.c; ctx.beginPath(); ctx.arc(X, Y, r, 0, 6.28); ctx.fill();
          if (d.personal) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(X, Y, r + 2.5, 0, 6.28); ctx.stroke(); }
          ctx.fillStyle = isHit ? "var(--text)" : "rgba(190,200,220,0.65)";
          ctx.font = (isHit ? "700 " : "500 ") + "11px Microsoft JhengHei, sans-serif"; ctx.textAlign = "center";
          ctx.fillText(d.src, X, Y - r - 5);
        });
        // 查詢點
        if (S.q) {
          const QX = px(S.q.x), QY = py(S.q.y), sc = Math.min(1, t * 1.4);
          ctx.save(); ctx.translate(QX, QY); ctx.rotate(Math.PI / 4); ctx.scale(sc, sc);
          ctx.fillStyle = hexA2("#ffffff", 0.25); ctx.fillRect(-12, -12, 24, 24);
          ctx.fillStyle = "#ffffff"; ctx.fillRect(-5.5, -5.5, 11, 11);
          ctx.restore();
          ctx.fillStyle = "#fff"; ctx.font = "700 11px Microsoft JhengHei, sans-serif"; ctx.textAlign = "center";
          ctx.fillText("查詢", QX, QY + 22);
        }
        if (S.t < 1) S.t = Math.min(1, S.t + 0.035);
      }
      function hexA2(hex, a) { const h = hex.replace("#", ""); const n = parseInt(h.length === 3 ? h.split("").map((x) => x + x).join("") : h, 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${Math.max(0, Math.min(1, a))})`; }

      function loop() {
        const panel = document.getElementById("panel");
        if (!document.body.contains(cv) || (panel && panel.classList.contains("hidden"))) return; // 面板關閉或內容替換即停
        draw(); requestAnimationFrame(loop);
      }
      requestAnimationFrame(() => { size(); search(c.querySelector("#d-q").value); loop(); });

      c.querySelector("#d-run").onclick = () => search(c.querySelector("#d-q").value);
      c.querySelectorAll(".vec-chip").forEach((chip) => chip.onclick = () => { const q = chip.textContent; c.querySelector("#d-q").value = q; search(q); });
    },

    /* ── LLM 供應商 ───────────────────────────────────── */
    llm(node, c) {
      c.innerHTML = `
        <p class="p-desc">分析師 + 預警員 + AI 助理共用<b>同一個</b>你在 sidebar 選的供應商。直接 HTTP 呼叫（不走 agent gateway，省冷啟動 30–60 秒）。</p>
        ${sh(node.color, "支援供應商")}
        <div class="card">
          ${L.LLM_PROVIDERS.map((p) => `<div class="card-row"><span class="k">${esc(p.name)}</span><span class="v">${esc(p.model)}</span></div>`).join("")}
        </div>
        ${sh(node.color, "call_llm_api 流程")}
        <div class="flow-steps">
          <div class="flow-step">依 provider 組 endpoint + headers（Anthropic 走 /v1/messages，其餘走 /chat/completions）</div>
          <div class="flow-step">送 system + user prompt（max_tokens 4096–8192，timeout 60–120s）</div>
          <div class="flow-step">偵測 <b>stop_reason=max_tokens</b> / finish_reason=length → 標示「回應可能被截斷」</div>
          <div class="flow-step">失敗寫 LAST_LLM_ERROR，UI 顯示 fallback（圖表仍照常）</div>
        </div>
        ${sh(node.color, "System Prompt")}
        <div class="codebox">你是台灣空氣品質多代理人系統中的一員。
重要：只能根據訊息中提供的具體數值作答，
禁止編造資料、城市或事件。回覆使用繁體中文。</div>`;
    },

    /* ── SQLite 時序快取 ──────────────────────────────── */
    sqlite(node, c) {
      c.innerHTML = `
        <p class="p-desc">純本機時序快取（<b>lobster_aqi.sqlite</b>），跨重啟保留。供「過去 7 天」紀錄板、本週對比、健康日誌相關性。</p>
        ${sh(node.color, "三張表（tsdb.py）")}
        <div class="card">
          <div class="card-row"><span class="k">aqi_snapshots</span><span class="v">每次 pipeline 快照</span></div>
          <div class="card-row"><span class="k">cams_hourly</span><span class="v">CAMS 過去 7 天逐時</span></div>
          <div class="card-row"><span class="k">health_diary</span><span class="v">每日症狀打卡</span></div>
        </div>
        ${sh(node.color, "health_diary schema")}
        <div class="codebox"><span class="ck">CREATE TABLE</span> health_diary (
  date TEXT, city_id TEXT,
  symptom_score INT, outdoor_min INT,
  note TEXT, created_at TEXT,
  <span class="ck">PRIMARY KEY</span> (date, city_id)   <span class="cm">-- 同日同城市可覆寫</span>
)</div>
        <p class="p-desc muted">寫入用 <b>UPSERT</b>（INSERT OR REPLACE）— 重跑不重複；created_at 保留首次建立時間。</p>`;
    },

    /* ── 資料匯出 latest_aqi.json ───────────────────────── */
    "export"(node, c) {
      c.innerHTML = `
        <p class="p-desc">Pipeline 跑完把這次結果寫成一份 JSON,放在專案的 <code>hermes_export/latest_aqi.json</code>,供 Agent Bot 拉取。</p>
        ${sh(node.color, "JSON 契約（節錄）")}
        <div class="codebox">{ <span class="ck">"data_mode"</span>: <span class="cs">"real"</span>,
  <span class="ck">"national"</span>: { <span class="ck">"avg_aqi"</span>: 42, <span class="ck">"worst"</span>: {…}, <span class="ck">"best"</span>: {…} },
  <span class="ck">"cities"</span>: [ {city, aqi, level, pm25, …} × 20 ],
  <span class="ck">"analyst_summary"</span>: <span class="cs">"…"</span>,
  <span class="ck">"advisories"</span>: { 城市名: 建議 },
  <span class="ck">"user_profile"</span>: { age, bmi, diagnoses, … } }</div>
        <p class="p-desc muted">由 data.build_hermes_payload() 產生;data_mode 誠實標 real / mock / demo。</p>`;
    },

    /* ── Agent Bot（拉取 latest_aqi.json）──────── */
    hermes(node, c) {
      c.innerHTML = `
        <p class="p-desc"><b>選填</b>(沒裝也能全功能跑)。任何 agent bot(Hermes / OpenClaw… 皆可)當聊天平台 bot,<b>來這裡讀</b> Pipeline 匯出的 <code>latest_aqi.json</code> 回答 —— 含使用者個人健康檔案,回答會個人化。<b>不用 webhook、不用 cron 指令。</b></p>
        ${sh(node.color, "怎麼運作（拉取模型）")}
        <div class="flow-steps">
          <div class="flow-step">① Pipeline 跑完 → 寫 latest_aqi.json</div>
          <div class="flow-step">② 使用者在聊天平台 @bot 問空品</div>
          <div class="flow-step">③ Agent Bot 讀 JSON（全台 + 分析 + persona）</div>
          <div class="flow-step">④ 回最新數據 + 個人化提醒</div>
        </div>
        ${sh(node.color, "本機驗證(以 Hermes 範例 skill)")}
        <div class="codebox">python hermes_skills/aqi-live/read_export.py <span class="cs">台中市</span></div>
        <p class="p-desc muted">skill 規格見 hermes_skills/aqi-live/SKILL.md;不需外部 API key。換別的 bot 框架也只要會讀這份 JSON。</p>`;
    },

    /* ── 聊天平台（使用者問 bot 的地方）──────────────────── */
    discord(node, c) {
      c.innerHTML = `
        <p class="p-desc">使用者在聊天平台(Discord / LINE / Slack…)<b>@bot</b> 問空品的地方。bot 讀 LobsterAQI 匯出的 latest_aqi.json 回答。</p>
        ${sh(node.color, "對話範例")}
        <div class="card">
          <div class="card-row"><span class="k">你</span><span class="v">@bot 台中現在空氣如何?</span></div>
          <div class="card-row"><span class="k">🤖 Bot</span><span class="v">📍 台中市 AQI 50（普通）…</span></div>
        </div>
        <p class="p-desc muted">不是 webhook 推送 —— 是你問、bot 才讀 JSON 回答(拉取模型)。</p>`;
    },
  };

  /* =======================================================================
   * 對外：render
   * ==================================================================== */
  const TAGS = {
    user: ["瀏覽器", "Streamlit 封面", "一鍵啟動"],
    app: ["Streamlit", "單頁 10 SECTION", "Plotly", "session_state"],
    collector: ["Agent A", "純 ETL · 無 LLM", "並行抓取", "資料清洗"],
    analyst: ["Agent B", "LLM 風險分析", "加權公式", "RAG"],
    advisor: ["Agent C", "LLM 個人化", "依個人檔案", "safe_hours"],
    epa: ["官方", "需 api_key", "aqx_p_432/488"],
    openmeteo: ["免金鑰", "CAMS 模式", "氣象"],
    civic: ["公開", "SensorThings", "Airbox", "清洗去重"],
    rag: ["n-gram 檢索", "WHO/EPA/Lancet", "1.4× 個人加權"],
    llm: ["多供應商", "直接 HTTP", "截斷偵測"],
    sqlite: ["本機快取", "3 張表", "UPSERT"],
    export: ["latest_aqi.json", "Pipeline 匯出", "供 Agent Bot 拉取"],
    hermes: ["選填", "Agent Bot", "讀 latest_aqi.json"],
    discord: ["使用者問 bot", "@mention", "拉取模型"],
  };
  const EYEBROW = {
    user: "ENTRY · 入口", app: "FRONTEND · 前端",
    collector: "PIPELINE · 第 1 步", analyst: "PIPELINE · 第 2 步", advisor: "PIPELINE · 第 3 步",
    epa: "DATA SOURCE · 資料源", openmeteo: "DATA SOURCE · 資料源", civic: "DATA SOURCE · 資料源",
    rag: "KNOWLEDGE · 知識庫", llm: "INFERENCE · 推論",
    sqlite: "STORAGE · 儲存", export: "EXPORT · 資料匯出", hermes: "BOT · Agent（選填）", discord: "CHANNEL · 聊天平台",
  };

  function render(id, container) {
    const node = L.NODES.find((n) => n.id === id);
    if (!node) return;
    container.innerHTML = header(node, EYEBROW[id] || "NODE", TAGS[id] || []);
    const body = document.createElement("div");
    container.appendChild(body);
    (BODY[id] || (() => { body.innerHTML = '<p class="p-desc muted">（無 demo）</p>'; }))(node, body);
    container.scrollTop = 0;
  }

  global.LOBSTER_DEMOS = { render };
})(window);
