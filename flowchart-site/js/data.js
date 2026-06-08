/* =============================================================================
 * data.js — LobsterAQI 專案模型（全部抽取自真實原始碼）
 * 提供：3D 節點 / 連線（資料流）/ 20 城市 / AQI 分級 / RAG 文獻 / LLM 供應商
 *       / 10 個 SECTION / 加權公式 / 敏感族群門檻
 * 所有數字與字串都對齊 aqi-tw-personal 的 data.py & app.py。
 * ========================================================================== */
(function (global) {
  "use strict";

  /* ── 配色（同專案 styles.py） ───────────────────────────── */
  const C = {
    bg: "#04060f", cyan: "#00d9ff", orange: "#ff8c42", green: "#00e676",
    yellow: "#ffd93d", red: "#ff4757", purple: "#9b59ff",
  };

  /* ── 20 縣市（data.py CITIES，含工業偏差 bias） ─────────── */
  const CITIES = [
    { id: "taipei",     name: "台北市", en: "Taipei",     region: "北部", bias: 0.95 },
    { id: "new_taipei", name: "新北市", en: "New Taipei", region: "北部", bias: 1.00 },
    { id: "taoyuan",    name: "桃園市", en: "Taoyuan",    region: "北部", bias: 1.10 },
    { id: "hsinchu",    name: "新竹市", en: "Hsinchu",    region: "北部", bias: 0.90 },
    { id: "keelung",    name: "基隆市", en: "Keelung",    region: "北部", bias: 0.80 },
    { id: "yilan",      name: "宜蘭縣", en: "Yilan",      region: "北部", bias: 0.55 },
    { id: "miaoli",     name: "苗栗縣", en: "Miaoli",     region: "中部", bias: 1.00 },
    { id: "taichung",   name: "台中市", en: "Taichung",   region: "中部", bias: 1.30 },
    { id: "changhua",   name: "彰化縣", en: "Changhua",   region: "中部", bias: 1.25 },
    { id: "nantou",     name: "南投縣", en: "Nantou",     region: "中部", bias: 0.85 },
    { id: "yunlin",     name: "雲林縣", en: "Yunlin",     region: "中部", bias: 1.45 }, // 麥寮六輕
    { id: "chiayi",     name: "嘉義市", en: "Chiayi",     region: "中部", bias: 1.20 },
    { id: "tainan",     name: "台南市", en: "Tainan",     region: "南部", bias: 1.25 },
    { id: "kaohsiung",  name: "高雄市", en: "Kaohsiung",  region: "南部", bias: 1.40 },
    { id: "pingtung",   name: "屏東縣", en: "Pingtung",   region: "南部", bias: 1.15 },
    { id: "hualien",    name: "花蓮縣", en: "Hualien",    region: "東部", bias: 0.55 },
    { id: "taitung",    name: "台東縣", en: "Taitung",    region: "東部", bias: 0.45 },
    { id: "penghu",     name: "澎湖縣", en: "Penghu",     region: "離島", bias: 0.50 },
    { id: "kinmen",     name: "金門縣", en: "Kinmen",     region: "離島", bias: 1.20 }, // 受陸源影響
    { id: "matsu",      name: "連江縣", en: "Matsu",      region: "離島", bias: 1.05 },
  ];

  /* ── AQI 6 級分級（data.py AQI_LEVELS） ────────────────── */
  const AQI_LEVELS = [
    { max: 50,  name: "良好",            color: "#00e676", level: 1 },
    { max: 100, name: "普通",            color: "#ffd93d", level: 2 },
    { max: 150, name: "對敏感族群不健康", color: "#ff8c42", level: 3 },
    { max: 200, name: "對所有族群不健康", color: "#ff4757", level: 4 },
    { max: 300, name: "非常不健康",      color: "#9b59ff", level: 5 },
    { max: 999, name: "危害",            color: "#7f0000", level: 6 },
  ];
  function aqiToLevel(aqi) {
    for (const lv of AQI_LEVELS) if (aqi <= lv.max) return lv;
    return AQI_LEVELS[AQI_LEVELS.length - 1];
  }

  const POLLUTANTS = ["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"];

  /* ── 分析師加權風險公式（app.py run_pipeline） ─────────── */
  const RISK_FORMULA = [
    { k: "PM2.5", w: 0.40 }, { k: "AQI", w: 0.20 }, { k: "O3", w: 0.15 },
    { k: "NO2", w: 0.10 }, { k: "SO2", w: 0.08 }, { k: "CO", w: 0.07 },
  ];

  /* ── RAG 預植入文獻（app.py RAG_SNIPPETS） ─────────────── */
  const RAG_SNIPPETS = [
    { source: "WHO Air Quality Guidelines 2021",
      quote: "PM2.5 年均不應超過 5 μg/m³，24 小時均值不應超過 15 μg/m³；長期暴露與心血管疾病、肺癌風險顯著相關。" },
    { source: "US EPA NAAQS",
      quote: "PM2.5 24 小時平均標準為 35 μg/m³，年均標準為 12 μg/m³；AQI > 100 屬於對敏感族群不健康。" },
    { source: "Lancet PM2.5 Cardiovascular 2023",
      quote: "高 PM2.5 暴露下進行劇烈戶外運動，肺部沉積量提升 3-5 倍；建議 AQI > 100 時改為室內活動。" },
    { source: "台灣空氣品質指標技術手冊",
      quote: "AQI 分六級：良好 (0-50)、普通 (51-100)、對敏感族群不健康 (101-150)、對所有族群不健康 (151-200)、非常不健康 (201-300)、危害 (>300)。" },
  ];

  /* ── 5 類敏感族群 + 容忍 AQI 門檻（app.py GROUP_AQI_LIMIT） ── */
  const SENSITIVE_GROUPS = [
    { id: "elderly",        name: "老人",   icon: "🧓", limit: 60 },
    { id: "children",       name: "幼童",   icon: "🧒", limit: 70 },
    { id: "asthma",         name: "氣喘",   icon: "🫁", limit: 50 },
    { id: "cardiovascular", name: "心血管", icon: "❤️", limit: 60 },
    { id: "pregnant",       name: "孕婦",   icon: "🤰", limit: 50 },
  ];

  /* ── LLM 供應商（data.py LLM_PROVIDERS） ───────────────── */
  const LLM_PROVIDERS = [
    { name: "Anthropic (Claude)", model: "claude-sonnet-4-6", api: "/v1/messages" },
    { name: "Google Gemini",      model: "gemini-2.5-flash",  api: "/v1beta/models" },
    { name: "MiniMax (國際版)",   model: "MiniMax-M2.7",      api: "/v1/text/chatcompletion_v2" },
    { name: "OpenAI",             model: "gpt-4o",            api: "/v1/chat/completions" },
    { name: "自訂 (OpenAI 相容)", model: "—",                 api: "/chat/completions" },
  ];

  /* ── 單頁 10 個 SECTION（README + app.py） ─────────────── */
  const SECTIONS = [
    { no: "01", name: "三隻 agent 協作",   icon: "🤝", desc: "像素風辦公室 + 3 個 agent 群組聊天室，逐步點亮跑分析" },
    { no: "02", name: "即時 AQI 主儀表板", icon: "📊", desc: "時間軸 scrubber + 聚焦城市 + 排名 + 地圖 + 散點 + 新鮮度燈號" },
    { no: "03", name: "24 小時趨勢",       icon: "📈", desc: "多城市 AQI 趨勢線，拖時間軸看任一時點快照" },
    { no: "04", name: "污染物剖析",        icon: "🧪", desc: "熱力圖 + 雷達圖 + 堆疊組成 + PM2.5 vs AQI 散點" },
    { no: "05", name: "環境關聯",          icon: "🌬️", desc: "濕度 vs PM2.5、風玫瑰圖" },
    { no: "06", name: "官方 vs 民間",      icon: "🛰️", desc: "EPA 測站對比 CivilIoT / LASS-net 微型感測器" },
    { no: "07", name: "健康預警",          icon: "🚨", desc: "每城市一張預警卡;有填個人檔案時展開為個人化建議" },
    { no: "08", name: "個人化推薦",        icon: "🩺", desc: "常駐城市 + 健康檔案 → 個人化健康指數卡 + 7 天趨勢" },
    { no: "09", name: "健康日誌",          icon: "📔", desc: "每日打卡（症狀分數 + 戶外時數）+ 症狀 vs AQI 相關性散點" },
    { no: "10", name: "Hermes Bot",        icon: "🪽", desc: "Pipeline 匯出 latest_aqi.json 供 Hermes（Discord bot）拉取回答 + 匯出狀態" },
  ];

  /* =========================================================================
   * 3D 節點：id / 顯示文字 / 類別色 / 座標 [x,y,z] / icon
   * 座標系：+y 上、中央直行為三代理人 pipeline，左側資料源、右側 LLM/輸出
   * ====================================================================== */
  // 村落／社區式佈局：各群「攤平」在地面上分成鄰里，三代理人為中央主街
  const NODES = [
    // 用戶層（前方，靠近鏡頭）
    { id: "user",     label: "使用者瀏覽器", sub: "localhost:8501", icon: "🧑‍💻", color: C.cyan,   pos: [0, 1.8, 14] },
    { id: "app",      label: "LobsterAQI",   sub: "Streamlit 單頁 · 10 SECTION", icon: "🦞", color: C.cyan, pos: [0, 1.8, 10] },

    // 三代理人 Pipeline（中央主街，前→後）
    { id: "collector", label: "採集者", sub: "Agent A · 純 ETL", icon: "📥", color: C.cyan,   pos: [0, 2.8, 5.5] },
    { id: "analyst",   label: "分析師", sub: "Agent B · 風險分析", icon: "🧠", color: C.purple, pos: [0, 2.8, 0] },
    { id: "advisor",   label: "預警員", sub: "Agent C · 健康預警", icon: "🩺", color: C.green,  pos: [0, 2.8, -5.5] },

    // 外部資料源（左側鄰里）
    { id: "epa",       label: "環境部 EPA",   sub: "aqx_p_432 / 488", icon: "🏛️", color: C.orange, pos: [-10, 1.7, 10] },
    { id: "openmeteo", label: "Open-Meteo / CAMS", sub: "氣象 + 大氣化學模式", icon: "🌦️", color: C.orange, pos: [-13.5, 2.1, 5] },
    { id: "civic",     label: "民間感測器",   sub: "民生公共物聯網 + LASS", icon: "📡", color: C.orange, pos: [-10, 1.7, 0.5] },

    // 外部服務整合（右側鄰里）
    { id: "rag",       label: "RAG 知識庫",   sub: "WHO/EPA/Lancet 文獻", icon: "📚", color: C.purple, pos: [10, 2.1, 6.5] },
    { id: "llm",       label: "LLM 供應商",   sub: "Claude / Gemini / …", icon: "✨", color: C.yellow, pos: [13.5, 2.1, 1] },
    { id: "hermes",    label: "Agent Bot", sub: "讀 JSON 在聊天室回答", icon: "🤖", color: C.purple, pos: [9.5, 1.6, -5] },
    { id: "discord",   label: "聊天平台", sub: "Discord / LINE / Slack…", icon: "💬", color: C.cyan,   pos: [13, 1.7, -9] },
    { id: "export",    label: "資料匯出", sub: "latest_aqi.json", icon: "📤", color: C.green,  pos: [4, 1.5, -8.5] },

    // 資料儲存層（後方）
    { id: "sqlite",    label: "SQLite 時序快取", sub: "lobster_aqi.sqlite", icon: "🗄️", color: C.green,  pos: [-5, 1.6, -10] },
  ];

  /* ── 連線（資料流）：from→to / 標籤 / 類別 / dashed=選填 ── */
  const EDGES = [
    { from: "user", to: "app",        label: "HTTP :8501", kind: "http" },
    { from: "app",  to: "collector",  label: "啟動 Pipeline", kind: "ctrl" },

    { from: "epa",       to: "collector", label: "即時 AQI", kind: "data" },
    { from: "openmeteo", to: "collector", label: "氣象 + CAMS", kind: "data" },
    { from: "civic",     to: "collector", label: "PM2.5 微型感測", kind: "data" },

    { from: "collector", to: "analyst", label: "資料封包 · 20 城市", kind: "data" },
    { from: "rag",       to: "analyst", label: "文獻片段", kind: "data" },
    { from: "llm",       to: "analyst", label: "風險報告", kind: "llm" },

    { from: "analyst",   to: "advisor", label: "風險分級", kind: "data" },
    { from: "llm",       to: "advisor", label: "個人化建議", kind: "llm" },

    { from: "advisor",   to: "sqlite",  label: "寫入快照", kind: "data" },
    { from: "advisor",   to: "export",  label: "匯出 JSON", kind: "data" },

    { from: "export",   to: "hermes",  label: "Hermes 拉取", kind: "pull", dashed: true },
    { from: "hermes",   to: "discord", label: "在頻道回答", kind: "pull", dashed: true },
  ];

  /* ── 各 kind 的線色 ──────────────────────────────────── */
  const EDGE_COLOR = {
    http: C.cyan, ctrl: "#8b95a8", data: C.cyan, llm: C.yellow, pull: C.purple,
  };

  /* =========================================================================
   * 確定性 AQI 產生器（移植 data.py 的 bias × 日夜雙峰 模型）
   * 讓採集者 demo 顯示「雲林高、台東低」這種符合真實的城市分佈
   * ====================================================================== */
  function diurnalFactor(hour) {
    const morning = Math.exp(-Math.pow(hour - 8, 2) / 8);
    const evening = Math.exp(-Math.pow(hour - 18, 2) / 10);
    return 0.7 + 0.45 * (morning + evening);
  }
  function hashStr(s) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  /** 回傳某城市在某小時的合成 AQI + 6 污染物（對齊 generate_current_snapshot） */
  function cityReading(city, hour) {
    const rng = mulberry32(hashStr(city.id + "-" + hour));
    const noise = (rng() - 0.5) * 20;                 // ≈ N(0,10)
    const diur = diurnalFactor(hour);
    const aqi = Math.max(15, Math.min(280, 55 * city.bias * diur + noise));
    const pm25 = Math.max(2, aqi * 0.45 + (rng() - 0.5) * 8);
    const pm10 = Math.max(5, pm25 * 1.6 + (rng() - 0.5) * 12);
    const o3 = Math.max(5, 40 + (aqi - 60) * 0.3 + (rng() - 0.5) * 16);
    const no2 = Math.max(2, 18 + aqi * 0.18 + (rng() - 0.5) * 8);
    const so2 = Math.max(0.5, 4 + aqi * 0.03 + (rng() - 0.5) * 3);
    const co = Math.max(0.1, 0.4 + aqi * 0.006 + (rng() - 0.5) * 0.2);
    return {
      city: city.name, region: city.region,
      aqi: Math.round(aqi),
      "PM2.5": Math.round(pm25), PM10: Math.round(pm10),
      O3: Math.round(o3), NO2: Math.round(no2),
      SO2: +so2.toFixed(1), CO: +co.toFixed(2),
      level: aqiToLevel(aqi),
    };
  }
  /** 全 20 城市快照（依 AQI 由高到低排序） */
  function snapshot(hour) {
    const now = (hour == null) ? new Date().getHours() : hour;
    return CITIES.map((c) => cityReading(c, now)).sort((a, b) => b.aqi - a.aqi);
  }

  /* =========================================================================
   * DIAGRAM — 分層架構圖模型（比照參考圖：用戶層 / 應用層 / 資料源 / 三代理人
   * / 外部服務 / 儲存層）。卡片含子步驟與輸出清單；demo 欄對應 demos.js 的節點。
   * ====================================================================== */
  const DIAGRAM = {
    userItems: [
      { icon: "🏠", name: "封面 + 個人健康檔案", sub: "步驟① 啟動前先填" },
      { icon: "📊", name: "10 個 SECTION", sub: "02-10 儀表板區" },
      { icon: "💬", name: "群組聊天室" },
      { icon: "🤖", name: "AI 助理" },
      { icon: "📍", name: "城市深入 Modal" },
      { icon: "↔️", name: "時間軸 Scrubber" },
      { icon: "📔", name: "健康日誌" },
      { icon: "🪽", name: "Hermes Bot 說明" },
    ],
    appBoxes: [
      { name: "UI Controller", sub: "頁面路由與狀態管理", demo: "app" },
      { name: "Session Manager", sub: "使用者會話與設定", demo: "app" },
      { name: "Pipeline Orchestrator", sub: "三代理人流程調度", demo: "app" },
    ],
    sources: [
      { id: "epa",       icon: "🏛️", name: "環境部 EPA",      lines: ["AQI 即時 (aqx_p_432)", "AQI 歷史 (aqx_p_488)"], demo: "epa" },
      { id: "civic",     icon: "☁️", name: "民生公共物聯網",  lines: ["SensorThings API", "智慧城鄉空品微型感測器"], demo: "civic" },
      { id: "lass",      icon: "🎯", name: "LASS-net Airbox",  lines: ["pm25.lass-net.org", "社群網路 · 補充離島"], demo: "civic" },
      { id: "openmeteo", icon: "⛅", name: "Open-Meteo",       lines: ["氣象資料 (免金鑰)"], demo: "openmeteo" },
      { id: "cams",      icon: "🌫️", name: "CAMS 模式預測",    lines: ["air-quality-api", "大氣化學模式 · 6h 預測"], demo: "openmeteo" },
    ],
    agents: [
      { id: "collector", num: "1", en: "Collector Agent", name: "採集者", tagline: "資料採集與整合 (純 ETL)", color: C.cyan, demo: "collector",
        steps: [{ icon: "📥", name: "資料擷取" }, { icon: "🧹", name: "資料清洗" }, { icon: "🔗", name: "資料整合" }, { icon: "🛡️", name: "品質檢查" }],
        outputs: ["即時 AQI 資料", "氣象資料", "民間感測器資料", "CAMS 預測資料"] },
      { id: "analyst", num: "2", en: "Analyst Agent", name: "分析師", tagline: "資料分析與風險評估 (LLM + RAG)", color: C.green, demo: "analyst",
        steps: [{ icon: "📈", name: "AQI 分析" }, { icon: "📉", name: "趨勢偵測" }, { icon: "📖", name: "RAG 檢索" }, { icon: "🌧️", name: "6h 預測" }],
        outputs: ["現況分析報告", "趨勢分析結果", "風險評估", "未來 6h 預測"] },
      { id: "advisor", num: "3", en: "Advisor Agent", name: "預警員", tagline: "個人化健康建議 (LLM,依個人檔案)", color: C.orange, demo: "advisor",
        steps: [{ icon: "📋", name: "讀個人檔案" }, { icon: "📊", name: "風險分級" }, { icon: "🩺", name: "個人化建議" }, { icon: "😷", name: "防護等級" }],
        outputs: ["個人化健康建議", "個人風險等級", "行動建議清單"] },
    ],
    services: [
      { id: "llm", icon: "🧠", name: "LLM 提供商", tag: "必填一個", color: C.purple, demo: "llm",
        items: ["Anthropic (Claude)", "Google Gemini", "MiniMax", "DeepSeek", "OpenAI", "自訂模型"] },
      { id: "hermes", icon: "🤖", name: "Agent Bot", tag: "選填", color: C.cyan, demo: "hermes",
        items: ["讀 latest_aqi.json", "在聊天平台回答空品", "依個人檔案個人化"],
        note: "拉取模型:Pipeline 匯出 JSON\nAgent Bot 來這裡讀並回答(Hermes / OpenClaw… 皆可)" },
    ],
    storage: ["AQI 即時快取", "歷史時序資料", "氣象與預測資料", "健康日誌資料", "使用者設定與訂閱"],
    flows: [
      { name: "即時資料流", color: C.cyan,   dashed: false },
      { name: "LLM 呼叫流", color: C.purple, dashed: true },
      { name: "Hermes 拉取流", color: C.purple, dashed: true },
      { name: "資料儲存流", color: C.green,  dashed: true },
    ],
    features: [
      { icon: "🗂️", name: "多源資料融合" },
      { icon: "👥", name: "三代理人協作" },
      { icon: "🧠", name: "AI 智慧分析" },
      { icon: "❤️", name: "個人化健康建議" },
      { icon: "🪽", name: "Hermes Bot 問答" },
    ],
  };

  /* =========================================================================
   * MODELS — 把 3D 場景的某個節點換成你自己的 glTF 模型（.glb / .gltf）
   *
   * 用法：
   *   1. 把模型檔放到 flowchart-site/models/ 資料夾
   *   2. 在下面用「節點 id」對應該檔，並調整 scale / rot / yOff / spin
   *   3. 用 python -m http.server 開網站（file:// 直接開會被瀏覽器擋住載入）
   *   找不到檔或載入失敗 → 自動退回原本的程序化模型（不會壞）。
   *
   * 節點 id：user / app / collector / analyst / advisor / epa / openmeteo /
   *          civic / rag / llm / sqlite / export / hermes / discord
   *
   * 欄位：url(檔案路徑) · scale(縮放) · rot([x,y,z] 弧度) · yOff(高度微調) · spin(自轉速度)
   * ====================================================================== */
  const MODELS = {
    // 三代理人 → 無人機（AI agent 風格，靠青/紫/綠光區分）
    collector: { url: "models/drone.glb", scale: 2.0, rot: [0, 0, 0], yOff: 0, spin: 0.5 },
    analyst:   { url: "models/drone.glb", scale: 2.0, rot: [0, 0.5, 0], yOff: 0, spin: 0.5 },
    advisor:   { url: "models/drone.glb", scale: 2.0, rot: [0, 1.0, 0], yOff: 0, spin: 0.5 },

    // 外部資料源
    epa:       { url: "models/tower.glb",     scale: 0.095, rot: [0, 0, 0], yOff: -1.75, spin: 0.15 }, // 官方監測塔
    openmeteo: { url: "models/satellite.glb", scale: 0.07, rot: [0, 0.3, 0], yOff: -0.4, spin: 0.3 },  // 氣象衛星
    civic:     { url: "models/antenna.glb",   scale: 4.0, rot: [0, 0, 0], yOff: 0.45, spin: 0.2 },     // 微型感測器/天線

    // LobsterAQI 本體 → 龍蝦,專案吉祥物(品牌保留;OpenClaw 推送/cron 已移除)
    app:       { url: "models/lobster.glb", scale: 0.55, rot: [0, 0.6, 0], yOff: 0, spin: 0.4 },

    // 其餘節點(含 hermes / export)用程序化模型。想換成自己的 .glb,照上面格式加一行即可。
  };

  /* ── 3D 場景的區域工作流標籤（對應架構圖的分層）──────── */
  const REGIONS = [
    { label: "用戶層",          pos: [0, 6.2, 12.5],  color: C.cyan },
    { label: "外部資料源",      pos: [-12, 6.6, 5],   color: C.orange },
    { label: "三代理人 Pipeline", pos: [0, 7.4, 0.5],  color: C.cyan },
    { label: "外部服務整合",    pos: [12, 6.6, 0.5],  color: C.purple },
    { label: "資料儲存層",      pos: [-5, 5.8, -10],  color: C.green },
  ];

  global.LOBSTER = {
    C, CITIES, AQI_LEVELS, aqiToLevel, POLLUTANTS, RISK_FORMULA,
    RAG_SNIPPETS, SENSITIVE_GROUPS, LLM_PROVIDERS, SECTIONS,
    NODES, EDGES, EDGE_COLOR, cityReading, snapshot, diurnalFactor, DIAGRAM, MODELS, REGIONS,
  };
})(window);
