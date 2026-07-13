(() => {
  "use strict";

  const STORAGE = {
    preferences: "aqi_preferences_v2",
    backend: "aqi_backend",
    theme: "aqi_theme",
  };
  const DEFAULT_PREFERENCES = {
    name: "",
    city: "taipei",
    sensitivity: "general",
    activity: "commute",
    threshold: 100,
  };
  const ACTIVITY_LABELS = {
    commute: "通勤",
    walk: "散步",
    run: "跑步",
    cycle: "單車",
    outdoor: "戶外工作",
  };
  const AGENT_LABELS = {
    coordinator: "協調者",
    collector: "採集者",
    analyst: "分析師",
    advisor: "顧問",
  };
  const SERIES_COLORS = ["#66e3d1", "#77a8ff", "#ff9e5c"];
  const STATIC_LATEST = "./data/latest_aqi.json";
  const STATIC_HISTORY = "./data/history.json";

  const $ = (id) => document.getElementById(id);
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const finite = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };
  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function readJsonStorage(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function readTextStorage(key, fallback = "") {
    try {
      return localStorage.getItem(key) || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function writeStorage(key, value) {
    try {
      localStorage.setItem(key, typeof value === "string" ? value : JSON.stringify(value));
    } catch (_) {
      showToast("瀏覽器阻擋了本機偏好儲存");
    }
  }

  function sanitizePreferences(raw = {}) {
    const sensitivity = raw.sensitivity === "sensitive" ? "sensitive" : "general";
    const activity = Object.hasOwn(ACTIVITY_LABELS, raw.activity) ? raw.activity : "commute";
    return {
      name: String(raw.name || "").trim().slice(0, 24),
      city: String(raw.city || "taipei"),
      sensitivity,
      activity,
      threshold: clamp(Math.round(finite(raw.threshold) ?? 100), 50, 180),
    };
  }

  try {
    // 舊版會把病歷與 BYO LLM 金鑰混在同一個設定物件；升級時主動清除。
    localStorage.removeItem("aqi_settings");
  } catch (_) {}

  const configuredBackend = String(window.AQI_CONFIG?.backendUrl || "").trim();
  const state = {
    latest: null,
    history: null,
    selectedCity: "taipei",
    compareCities: [],
    trendHours: 24,
    preferences: sanitizePreferences(readJsonStorage(STORAGE.preferences, DEFAULT_PREFERENCES)),
    backend: normalizeBackend(readTextStorage(STORAGE.backend, configuredBackend)),
    backendOnline: false,
    health: null,
    loadSequence: 0,
    rankingBound: false,
    runningAgents: false,
    lastFocus: null,
    toastTimer: null,
  };

  function normalizeBackend(value) {
    return String(value || "").trim().replace(/\/+$/, "");
  }

  function apiUrl(path) {
    return `${state.backend}${path}`;
  }

  function parseTaipeiDate(value) {
    if (!value) return null;
    const text = String(value).trim();
    const zoned = /(?:Z|[+-]\d\d:\d\d)$/i.test(text) ? text : `${text}+08:00`;
    const date = new Date(zoned);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function sourceAgeMinutes() {
    const date = parseTaipeiDate(state.latest?.generated_at);
    return date ? Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000)) : null;
  }

  function formatAge(minutes) {
    if (minutes === null) return "更新時間未知";
    if (minutes < 2) return "剛剛更新";
    if (minutes < 60) return `${minutes} 分鐘前更新`;
    if (minutes < 1440) return `${Math.floor(minutes / 60)} 小時前更新`;
    return `${Math.floor(minutes / 1440)} 天前更新`;
  }

  function formatTimestamp(value) {
    const date = parseTaipeiDate(value);
    if (!date) return "時間未知";
    return new Intl.DateTimeFormat("zh-TW", {
      timeZone: "Asia/Taipei",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }

  function aqiInfo(value) {
    const aqi = finite(value) ?? 0;
    if (aqi <= 50) return { level: "良好", color: "var(--aqi-good)" };
    if (aqi <= 100) return { level: "普通", color: "var(--aqi-moderate)" };
    if (aqi <= 150) return { level: "對敏感族群不健康", color: "var(--aqi-sensitive)" };
    if (aqi <= 200) return { level: "對所有族群不健康", color: "var(--aqi-unhealthy)" };
    if (aqi <= 300) return { level: "非常不健康", color: "var(--aqi-very)" };
    return { level: "危害", color: "var(--aqi-hazard)" };
  }

  function numberText(value, digits = 0) {
    const n = finite(value);
    return n === null ? "—" : n.toFixed(digits);
  }

  async function fetchJson(url, options = {}, timeoutMs = 9000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        cache: "no-store",
        ...options,
        signal: controller.signal,
      });
      if (!response.ok) {
        let detail = "";
        try {
          const body = await response.json();
          detail = body.detail || body.error || "";
        } catch (_) {}
        throw new Error(detail || `HTTP ${response.status}`);
      }
      return await response.json();
    } finally {
      clearTimeout(timer);
    }
  }

  function validateLatest(payload) {
    if (!payload || !Array.isArray(payload.cities) || !payload.cities.length) {
      throw new Error("資料格式不完整：缺少城市快照");
    }
    return payload;
  }

  async function loadData(preferBackend = state.backendOnline) {
    const sequence = ++state.loadSequence;
    setLoadingStatus();
    let latest;
    let history = null;
    let usedBackend = false;

    if (preferBackend && state.backend) {
      try {
        const results = await Promise.all([
          fetchJson(apiUrl("/api/snapshot")),
          fetchJson(apiUrl("/api/history")).catch(() => null),
        ]);
        latest = validateLatest(results[0]);
        history = results[1];
        usedBackend = true;
      } catch (error) {
        state.backendOnline = false;
        state.health = null;
        updateBackendUI();
        showToast(`後端資料讀取失敗，已改用靜態快照：${error.message}`);
      }
    }

    if (!latest) {
      const results = await Promise.all([
        fetchJson(STATIC_LATEST),
        fetchJson(STATIC_HISTORY).catch(() => null),
      ]);
      latest = validateLatest(results[0]);
      history = results[1];
    }

    if (sequence !== state.loadSequence) return;
    state.latest = latest;
    state.history = history;
    const ids = new Set(latest.cities.map((city) => city.city_id));
    const preferred = ids.has(state.preferences.city) ? state.preferences.city : null;
    if (!ids.has(state.selectedCity)) state.selectedCity = preferred || latest.cities[0].city_id;
    state.compareCities = state.compareCities.filter((id) => ids.has(id));
    renderAll();

    if (usedBackend) {
      $("agent-hint").firstChild.textContent = "流程狀態來自後端 SSE，不使用假動畫。 ";
    }
  }

  function setLoadingStatus() {
    const pill = $("live-status");
    pill.className = "live-pill";
    pill.querySelector("span").textContent = "資料載入中";
    $("freshness").textContent = "正在取得城市快照…";
  }

  function showLoadError(error) {
    const alert = $("data-alert");
    alert.hidden = false;
    alert.dataset.tone = "danger";
    $("data-alert-title").textContent = "資料載入失敗";
    $("data-alert-text").textContent = `${error.message}。請使用 HTTP 伺服器開啟網站，或檢查 data 目錄。`;
    const pill = $("live-status");
    pill.className = "live-pill stale";
    pill.querySelector("span").textContent = "無可用資料";
    $("freshness").textContent = "請稍後重試";
  }

  function cityById(id) {
    return state.latest?.cities?.find((city) => city.city_id === id) || null;
  }

  function nationalSummary() {
    const cities = state.latest?.cities || [];
    if (!cities.length) return { avg_aqi: null, worst: null, best: null };
    const sorted = [...cities].sort((a, b) => (finite(b.aqi) ?? -1) - (finite(a.aqi) ?? -1));
    const avg = cities.reduce((sum, city) => sum + (finite(city.aqi) ?? 0), 0) / cities.length;
    return state.latest.national?.worst && state.latest.national?.best
      ? state.latest.national
      : { avg_aqi: avg, worst: sorted[0], best: sorted.at(-1) };
  }

  function renderAll() {
    if (!state.latest) return;
    renderDataStatus();
    renderProfileChrome();
    renderSelectOptions();
    renderHero();
    renderNational();
    renderRegionFilter();
    renderCityGrid();
    renderCompare();
    renderCityDetail();
    renderAnalyst();
    renderRanking();
    renderTrend();
  }

  function renderDataStatus() {
    const mode = String(state.latest.data_mode || "unknown").toLowerCase();
    const age = sourceAgeMinutes();
    const stale = age === null || age > 120;
    const simulated = mode !== "real";
    const alert = $("data-alert");
    const modeBadge = $("mode-badge");
    const pill = $("live-status");

    $("freshness").textContent = `${formatAge(age)} · ${formatTimestamp(state.latest.generated_at)}`;
    pill.className = `live-pill ${stale ? "stale" : "online"}`;
    pill.querySelector("span").textContent = stale ? "歷史快照" : (simulated ? "展示資料" : "即時資料");

    modeBadge.hidden = !simulated;
    modeBadge.textContent = mode === "mock" ? "模擬資料" : mode.toUpperCase();

    if (stale || simulated) {
      alert.hidden = false;
      alert.dataset.tone = stale ? "danger" : "warning";
      $("data-alert-title").textContent = stale ? "這不是即時資料" : "目前為展示資料";
      const parts = [];
      if (stale) parts.push(`快照已是 ${formatAge(age).replace("更新", "")}，請勿當成現在的空氣狀況`);
      if (simulated) parts.push("數值為模擬或備援資料，只適合檢查介面與流程");
      $("data-alert-text").textContent = `${parts.join("；")}。`;
    } else {
      alert.hidden = true;
      delete alert.dataset.tone;
    }
  }

  function renderProfileChrome() {
    const name = state.preferences.name;
    $("profile-avatar").textContent = name ? Array.from(name)[0] : "你";
    $("profile-button-name").textContent = name || "建立個人偏好";
  }

  function fillCitySelect(select, selected) {
    const fragment = document.createDocumentFragment();
    for (const city of state.latest.cities) {
      const option = document.createElement("option");
      option.value = city.city_id;
      option.textContent = city.city;
      option.selected = city.city_id === selected;
      fragment.append(option);
    }
    select.replaceChildren(fragment);
  }

  function renderSelectOptions() {
    fillCitySelect($("home-city-select"), state.selectedCity);
    fillCitySelect($("city-select"), state.selectedCity);
    fillCitySelect($("set-city"), state.preferences.city);
  }

  function renderHero() {
    const city = cityById(state.selectedCity);
    if (!city) return;
    const info = aqiInfo(city.aqi);
    const hour = new Date().getHours();
    const salutation = hour < 11 ? "早安" : hour < 18 ? "午安" : "晚安";
    $("greeting").textContent = state.preferences.name
      ? `${salutation}，${state.preferences.name}。這是你的空氣行動卡`
      : `${salutation}，先看看今天的空氣`;
    $("hero-city").textContent = city.city;
    $("hero-aqi").textContent = numberText(city.aqi, 0);
    $("hero-level").textContent = info.level;
    $("hero-card").style.setProperty("--aqi-color", info.color);

    const age = sourceAgeMinutes();
    const limited = state.latest.data_mode !== "real" || age === null || age > 120;
    const thresholdHit = (finite(city.aqi) ?? 0) >= state.preferences.threshold;
    if (limited) {
      $("hero-summary").textContent = "資料不是即時實測；下方先給保守的介面示範，出門前請再確認官方即時資訊。";
    } else if (thresholdHit) {
      $("hero-summary").textContent = `AQI 已達你的提醒門檻 ${state.preferences.threshold}，今天的活動安排建議更保守。`;
    } else {
      const sensitive = state.preferences.sensitivity === "sensitive" ? "較敏感模式" : "一般模式";
      $("hero-summary").textContent = `依你的${sensitive}與${ACTIVITY_LABELS[state.preferences.activity]}需求，整理三項可直接採取的行動。`;
    }

    const plan = personalPlan(city, limited);
    $("plan-outdoor").textContent = plan.outdoor;
    $("plan-mask").textContent = plan.mask;
    $("plan-window").textContent = plan.window;
  }

  function personalPlan(city, limited) {
    const aqi = finite(city.aqi) ?? 999;
    const isSensitive = state.preferences.sensitivity === "sensitive";
    const highIntensity = ["run", "cycle", "outdoor"].includes(state.preferences.activity);
    const activity = ACTIVITY_LABELS[state.preferences.activity];
    const thresholdHit = aqi >= state.preferences.threshold;
    let result;

    if (aqi <= 50 && !thresholdHit) {
      result = { outdoor: `適合${activity}`, mask: "一般不需要", window: "可以通風" };
    } else if (aqi <= 100 && !thresholdHit) {
      result = {
        outdoor: isSensitive || highIntensity ? `縮短${activity}時間` : `${activity}可照常`,
        mask: isSensitive ? "人多處可備口罩" : "依體感準備",
        window: "短時間通風",
      };
    } else if (aqi <= 150) {
      result = {
        outdoor: highIntensity ? "改低強度或室內" : `縮短${activity}時間`,
        mask: "外出建議適當防護",
        window: "關窗並持續觀察",
      };
    } else if (aqi <= 200) {
      result = { outdoor: "避免長時間戶外", mask: "外出加強防護", window: "關窗並開啟淨化" };
    } else {
      result = { outdoor: "非必要先不外出", mask: "必要外出嚴格防護", window: "停止戶外通風" };
    }

    if (limited) {
      result.outdoor = `保守安排：${result.outdoor}`;
      result.mask = `先備妥：${result.mask}`;
      result.window = `先確認即時值：${result.window}`;
    }
    return result;
  }

  function renderNational() {
    const national = nationalSummary();
    $("kpi-avg").textContent = numberText(national.avg_aqi, 0);
    $("kpi-worst").textContent = national.worst?.city || "—";
    $("kpi-worst-foot").textContent = national.worst ? `AQI ${numberText(national.worst.aqi, 0)}` : "";
    $("kpi-best").textContent = national.best?.city || "—";
    $("kpi-best-foot").textContent = national.best ? `AQI ${numberText(national.best.aqi, 0)}` : "";
  }

  function renderRegionFilter() {
    const select = $("region-filter");
    const current = select.value || "all";
    const regions = [...new Set(state.latest.cities.map((city) => city.region).filter(Boolean))];
    select.replaceChildren(new Option("所有區域", "all"), ...regions.map((region) => new Option(region, region)));
    select.value = regions.includes(current) ? current : "all";
  }

  function filteredCities() {
    const query = $("city-search").value.trim().toLocaleLowerCase("zh-Hant");
    const region = $("region-filter").value;
    const sort = $("sort-select").value;
    const rows = state.latest.cities.filter((city) => {
      const matchesQuery = !query || `${city.city} ${city.city_id}`.toLocaleLowerCase("zh-Hant").includes(query);
      return matchesQuery && (region === "all" || city.region === region);
    });
    rows.sort((a, b) => {
      if (sort === "aqi-asc") return (finite(a.aqi) ?? 999) - (finite(b.aqi) ?? 999);
      if (sort === "name") return String(a.city).localeCompare(String(b.city), "zh-Hant");
      return (finite(b.aqi) ?? -1) - (finite(a.aqi) ?? -1);
    });
    return rows;
  }

  function renderCityGrid() {
    const rows = filteredCities();
    const grid = $("city-grid");
    if (!rows.length) {
      grid.innerHTML = '<p class="empty-state">找不到符合條件的城市，試試其他關鍵字。</p>';
      return;
    }
    grid.innerHTML = rows.map((city) => {
      const info = aqiInfo(city.aqi);
      const compared = state.compareCities.includes(city.city_id);
      return `
        <article class="city-tile ${city.city_id === state.selectedCity ? "active" : ""}" style="--tile-color:${info.color}">
          <button class="city-tile-main" type="button" data-action="select" data-city="${escapeHtml(city.city_id)}" aria-label="查看 ${escapeHtml(city.city)} 詳情">
            <span class="city-tile-top"><span class="city-tile-name">${escapeHtml(city.city)}</span><strong class="city-tile-aqi">${numberText(city.aqi, 0)}</strong></span>
            <span class="city-tile-meta"><span>${escapeHtml(city.region || "未分類")}</span><span>${escapeHtml(info.level)}</span></span>
          </button>
          <button class="compare-toggle" type="button" data-action="compare" data-city="${escapeHtml(city.city_id)}" aria-pressed="${compared}">${compared ? "已加入比較" : "＋ 加入比較"}</button>
        </article>`;
    }).join("");
  }

  function renderCompare() {
    const panel = $("compare-panel");
    const cities = state.compareCities.map(cityById).filter(Boolean);
    panel.hidden = cities.length === 0;
    $("compare-cities").innerHTML = cities.map((city) => `<span class="compare-chip">${escapeHtml(city.city)}</span>`).join("");
    if (!cities.length) return;
    if (cities.length < 2) {
      chartPlaceholder($("compare-chart"), "再選一座城市，就能比較近期曲線。");
      return;
    }
    renderCompareChart(cities);
  }

  function selectCity(id, { saveHome = false, scroll = false } = {}) {
    if (!cityById(id)) return;
    state.selectedCity = id;
    if (saveHome) {
      state.preferences.city = id;
      writeStorage(STORAGE.preferences, state.preferences);
    }
    renderAll();
    if (scroll) $("city-title").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function toggleCompare(id) {
    const index = state.compareCities.indexOf(id);
    if (index >= 0) {
      state.compareCities.splice(index, 1);
    } else if (state.compareCities.length >= 3) {
      showToast("最多同時比較三座城市");
      return;
    } else {
      state.compareCities.push(id);
    }
    renderCityGrid();
    renderCompare();
  }

  function renderCityDetail() {
    const city = cityById(state.selectedCity);
    if (!city) return;
    const info = aqiInfo(city.aqi);
    $("city-title").textContent = `${city.city} 詳情`;
    renderGauge(city, info);
    const pollutants = [
      ["PM2.5", city.pm25, "µg/m³", 1],
      ["PM10", city.pm10, "µg/m³", 1],
      ["O₃", city.o3, "ppb", 1],
      ["NO₂", city.no2, "ppb", 1],
      ["SO₂", city.so2, "ppb", 2],
      ["CO", city.co, "ppm", 2],
    ];
    $("pollutants").innerHTML = pollutants.map(([name, value, unit, digits]) => `
      <div class="poll"><span class="poll-name">${name}</span><div class="poll-val">${numberText(value, digits)}<span class="poll-unit">${unit}</span></div></div>
    `).join("");
  }

  function renderGauge(city, info) {
    const value = clamp(finite(city.aqi) ?? 0, 0, 300);
    const radius = 66;
    const circumference = 2 * Math.PI * radius;
    const filled = circumference * (value / 300);
    const gauge = $("gauge");
    gauge.setAttribute("aria-label", `${city.city} AQI ${numberText(city.aqi, 0)}，${info.level}`);
    gauge.innerHTML = `
      <svg viewBox="0 0 160 160" aria-hidden="true">
        <circle class="gauge-track" cx="80" cy="80" r="${radius}"></circle>
        <circle class="gauge-value" cx="80" cy="80" r="${radius}" stroke="${info.color}" stroke-dasharray="${filled} ${circumference}"></circle>
      </svg>
      <div class="gauge-center"><strong class="gauge-num">${numberText(city.aqi, 0)}</strong><span class="gauge-lv" style="background:${info.color}">${escapeHtml(info.level)}</span></div>`;
  }

  function historySeries(id) {
    const raw = state.history?.cities?.[id]?.points;
    if (!Array.isArray(raw) || !raw.length) return [];
    const dated = raw.map((point) => ({ ...point, date: parseTaipeiDate(point.t) })).filter((point) => point.date);
    if (!dated.length) return [];
    const max = Math.max(...dated.map((point) => point.date.getTime()));
    const cutoff = max - state.trendHours * 3600000;
    return dated.filter((point) => point.date.getTime() >= cutoff);
  }

  function plotTheme() {
    const light = document.documentElement.dataset.theme === "light";
    return {
      paper: "rgba(0,0,0,0)",
      plot: "rgba(0,0,0,0)",
      text: light ? "#405867" : "#91a4b9",
      grid: light ? "rgba(38,73,92,.12)" : "rgba(164,196,224,.12)",
    };
  }

  function baseLayout(extra = {}) {
    const theme = plotTheme();
    return {
      autosize: true,
      paper_bgcolor: theme.paper,
      plot_bgcolor: theme.plot,
      font: { family: 'Inter, "Noto Sans TC", sans-serif', color: theme.text, size: 11 },
      margin: { l: 40, r: 12, t: 14, b: 40 },
      hoverlabel: { bgcolor: document.documentElement.dataset.theme === "light" ? "#fff" : "#102136", bordercolor: "rgba(120,150,170,.25)", font: { color: document.documentElement.dataset.theme === "light" ? "#122331" : "#f5f8fc" } },
      xaxis: { gridcolor: theme.grid, zeroline: false, automargin: true },
      yaxis: { gridcolor: theme.grid, zeroline: false, automargin: true },
      showlegend: false,
      ...extra,
    };
  }

  function plotConfig() {
    return { responsive: true, displayModeBar: false, scrollZoom: false };
  }

  function chartPlaceholder(element, text) {
    element.innerHTML = `<div class="chart-placeholder">${escapeHtml(text)}</div>`;
  }

  function preparePlot(element) {
    if (element.querySelector(".chart-placeholder")) element.replaceChildren();
  }

  function renderTrend() {
    const element = $("trend");
    const city = cityById(state.selectedCity);
    const points = historySeries(state.selectedCity);
    element.setAttribute("aria-label", city ? `${city.city} 最近 ${state.trendHours} 小時 AQI 趨勢` : "AQI 趨勢");
    if (!window.Plotly) return chartPlaceholder(element, "圖表元件載入中；城市數值仍可正常閱讀。");
    if (!points.length) return chartPlaceholder(element, "這座城市目前沒有歷史時序資料。");
    const info = aqiInfo(city.aqi);
    preparePlot(element);
    window.Plotly.react(element, [{
      x: points.map((point) => point.date),
      y: points.map((point) => finite(point.aqi)),
      type: "scatter",
      mode: "lines+markers",
      line: { color: info.color, width: 3, shape: "spline" },
      marker: { color: info.color, size: 5 },
      fill: "tozeroy",
      fillcolor: "rgba(102,227,209,.08)",
      hovertemplate: "%{x|%m/%d %H:%M}<br>AQI %{y:.0f}<extra></extra>",
    }], baseLayout({
      xaxis: { ...baseLayout().xaxis, type: "date", tickformat: "%H:%M" },
      yaxis: { ...baseLayout().yaxis, rangemode: "tozero", title: "AQI" },
    }), plotConfig());
  }

  function renderCompareChart(cities) {
    const element = $("compare-chart");
    if (!window.Plotly) return chartPlaceholder(element, "圖表元件載入中；稍後會自動顯示比較曲線。");
    const traces = cities.map((city, index) => {
      const points = historySeries(city.city_id);
      return {
        name: city.city,
        x: points.map((point) => point.date),
        y: points.map((point) => finite(point.aqi)),
        type: "scatter",
        mode: "lines",
        line: { color: SERIES_COLORS[index], width: 3, shape: "spline" },
        hovertemplate: `${escapeHtml(city.city)}<br>%{x|%m/%d %H:%M}<br>AQI %{y:.0f}<extra></extra>`,
      };
    }).filter((trace) => trace.x.length);
    if (!traces.length) return chartPlaceholder(element, "所選城市沒有可比較的歷史時序。");
    element.setAttribute("aria-label", `${cities.map((city) => city.city).join("、")}最近 ${state.trendHours} 小時 AQI 比較`);
    preparePlot(element);
    window.Plotly.react(element, traces, baseLayout({
      showlegend: true,
      legend: { orientation: "h", y: 1.12, x: 0 },
      xaxis: { ...baseLayout().xaxis, type: "date", tickformat: "%H:%M" },
      yaxis: { ...baseLayout().yaxis, rangemode: "tozero", title: "AQI" },
    }), plotConfig());
  }

  function renderRanking() {
    const element = $("ranking");
    const cities = [...state.latest.cities].sort((a, b) => (finite(a.aqi) ?? 0) - (finite(b.aqi) ?? 0));
    element.setAttribute("aria-label", `全台 AQI 排行；最高為 ${cities.at(-1)?.city || "未知"}，最低為 ${cities[0]?.city || "未知"}`);
    if (!window.Plotly) return chartPlaceholder(element, "圖表元件載入中；全國摘要仍可正常閱讀。");
    preparePlot(element);
    window.Plotly.react(element, [{
      x: cities.map((city) => finite(city.aqi)),
      y: cities.map((city) => city.city),
      customdata: cities.map((city) => city.city_id),
      type: "bar",
      orientation: "h",
      marker: { color: cities.map((city) => aqiInfo(city.aqi).color), line: { width: 0 } },
      hovertemplate: "%{y}<br>AQI %{x:.0f}<extra>點擊查看</extra>",
    }], baseLayout({
      margin: { l: 68, r: 16, t: 8, b: 34 },
      xaxis: { ...baseLayout().xaxis, rangemode: "tozero", title: "AQI" },
      yaxis: { ...baseLayout().yaxis, gridcolor: "rgba(0,0,0,0)", tickfont: { size: 10 } },
    }), plotConfig()).then(() => {
      if (state.rankingBound || typeof element.on !== "function") return;
      state.rankingBound = true;
      element.on("plotly_click", (event) => {
        const id = event?.points?.[0]?.customdata;
        if (id) selectCity(id, { scroll: true });
      });
    });
  }

  function renderAnalyst() {
    const text = String(state.latest.analyst_summary || "").trim();
    $("analyst").hidden = !text;
    $("analyst-text").textContent = text;
  }

  function applyTheme(theme) {
    const safe = theme === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = safe;
    $("theme-icon").textContent = safe === "light" ? "☀" : "☾";
    $("theme-label").textContent = safe === "light" ? "淺色" : "深色";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", safe === "light" ? "#f0f5f8" : "#08111f");
    writeStorage(STORAGE.theme, safe);
    if (state.latest) {
      renderRanking();
      renderTrend();
      renderCompare();
    }
  }

  function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => { toast.hidden = true; }, 3400);
  }

  function setPageInert(inert) {
    for (const selector of [".topbar", "main", ".site-foot", "#chat-fab", "#chat-panel"]) {
      const element = document.querySelector(selector);
      if (element) element.inert = inert;
    }
  }

  function populateSettings() {
    $("set-name").value = state.preferences.name;
    if (state.latest) fillCitySelect($("set-city"), state.preferences.city);
    $("set-sensitivity").value = state.preferences.sensitivity;
    $("set-activity").value = state.preferences.activity;
    $("set-threshold").value = String(state.preferences.threshold);
    $("set-thr-val").textContent = String(state.preferences.threshold);
    $("set-backend-url").value = state.backend;
    $("set-backend-status").textContent = state.backendOnline ? "已連線" : "未連線";
  }

  function openSettings() {
    state.lastFocus = document.activeElement;
    populateSettings();
    $("sidebar-backdrop").hidden = false;
    $("sidebar").hidden = false;
    $("settings-btn").setAttribute("aria-expanded", "true");
    setPageInert(true);
    requestAnimationFrame(() => $("sidebar").focus());
  }

  function closeSettings() {
    $("sidebar-backdrop").hidden = true;
    $("sidebar").hidden = true;
    $("settings-btn").setAttribute("aria-expanded", "false");
    setPageInert(false);
    state.lastFocus?.focus?.();
  }

  function trapSidebarFocus(event) {
    if (event.key !== "Tab" || $("sidebar").hidden) return;
    const focusable = [...$("sidebar").querySelectorAll('button, input, select, summary, [tabindex]:not([tabindex="-1"])')]
      .filter((element) => !element.disabled && element.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function validBackend(value) {
    if (!value) return true;
    try {
      const url = new URL(value);
      if (!["http:", "https:"].includes(url.protocol)) return false;
      const local = ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
      if (location.protocol === "https:" && url.protocol !== "https:" && !local) return false;
      return true;
    } catch (_) {
      return false;
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    const backend = normalizeBackend($("set-backend-url").value);
    if (!validBackend(backend)) {
      showToast("請輸入完整的 HTTP(S) 後端網址；公開 HTTPS 網站必須搭配 HTTPS API");
      $("set-backend-url").focus();
      return;
    }
    state.preferences = sanitizePreferences({
      name: $("set-name").value,
      city: $("set-city").value,
      sensitivity: $("set-sensitivity").value,
      activity: $("set-activity").value,
      threshold: $("set-threshold").value,
    });
    state.backend = backend;
    state.selectedCity = cityById(state.preferences.city) ? state.preferences.city : state.selectedCity;
    writeStorage(STORAGE.preferences, state.preferences);
    writeStorage(STORAGE.backend, state.backend);
    closeSettings();
    renderAll();
    showToast("個人偏好已套用");
    await checkBackend();
    if (state.backendOnline) await loadData(true);
  }

  function resetSettings() {
    state.preferences = { ...DEFAULT_PREFERENCES };
    state.backend = configuredBackend;
    state.backendOnline = false;
    state.health = null;
    if (cityById(state.preferences.city)) state.selectedCity = state.preferences.city;
    try {
      localStorage.removeItem(STORAGE.preferences);
      localStorage.removeItem(STORAGE.backend);
      localStorage.removeItem("aqi_settings");
    } catch (_) {}
    populateSettings();
    renderAll();
    updateBackendUI();
    showToast("這台裝置上的偏好已清除");
  }

  async function checkBackend() {
    state.backendOnline = false;
    state.health = null;
    if (!state.backend) {
      updateBackendUI();
      return false;
    }
    try {
      const health = await fetchJson(apiUrl("/api/health"), {}, 4500);
      state.backendOnline = health?.ok === true;
      state.health = health;
    } catch (_) {
      state.backendOnline = false;
    }
    updateBackendUI();
    return state.backendOnline;
  }

  function updateBackendUI() {
    const chip = $("backend-chip");
    chip.classList.toggle("online", state.backendOnline);
    if (state.backendOnline) {
      chip.textContent = state.health?.agentic ? "後端已連線 · Agentic" : "後端已連線";
      $("agent-hint").firstChild.textContent = "流程狀態來自後端 SSE，不使用假動畫。 ";
      $("set-backend").textContent = "變更連線";
    } else {
      chip.textContent = state.backend ? "後端無回應" : "後端未連線";
      $("agent-hint").firstChild.textContent = "連上 FastAPI 後即可執行真實流程。 ";
      $("set-backend").textContent = "設定後端";
    }
    $("run-agents").disabled = !state.backendOnline || state.runningAgents;
    $("set-backend-status").textContent = state.backendOnline ? "已連線" : "未連線";
  }

  function backendProfile() {
    return {
      age: 0,
      sex: "prefer_not",
      height_cm: 0,
      weight_kg: 0,
      diagnoses: [],
      med_history: "",
      city: state.preferences.city || state.selectedCity,
      threshold: state.preferences.threshold,
      preferences_enabled: true,
      sensitivity: state.preferences.sensitivity,
      activity: state.preferences.activity,
    };
  }

  function setAgentState(agent, status, label) {
    const node = $(`agent-node-${agent}`);
    if (!node) return;
    node.dataset.state = status;
    const stateLabel = node.querySelector('[data-role="state"]');
    if (stateLabel) stateLabel.textContent = label;
  }

  function resetAgentFlow() {
    for (const agent of ["coordinator", "collector", "analyst", "advisor"]) setAgentState(agent, "idle", "待命");
    $("agent-flow").setAttribute("aria-busy", "false");
    $("agent-log").replaceChildren();
    $("agent-log").hidden = true;
    $("agent-result").hidden = true;
    $("agent-result").replaceChildren();
  }

  function addAgentLog(agent, text, dim = false) {
    const log = $("agent-log");
    log.hidden = false;
    const line = document.createElement("div");
    line.className = "ln";
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = AGENT_LABELS[agent] || "系統";
    const message = document.createElement("span");
    if (dim) message.className = "dim";
    message.textContent = text;
    line.append(who, message);
    log.append(line);
    log.scrollTop = log.scrollHeight;
  }

  function handleAgentEvent(event) {
    const agent = String(event.agent || "coordinator");
    if (event.kind === "agent_start") {
      setAgentState(agent, "running", "執行中");
      addAgentLog(agent, `${event.name || AGENT_LABELS[agent] || "Agent"}開始工作`);
    } else if (event.kind === "agent_done") {
      setAgentState(agent, "done", "完成");
      const detail = event.cities ? `完成 ${event.cities} 座城市` : event.chars ? `產出 ${event.chars} 字` : "工作完成";
      addAgentLog(agent, detail);
    } else if (event.kind === "agent_note") {
      addAgentLog(agent, event.text || "流程備註", true);
      if (agent === "coordinator" && String(event.text || "").includes("略過")) {
        setAgentState("analyst", "skipped", "已略過");
        setAgentState("advisor", "skipped", "已略過");
      }
    } else if (event.kind === "tool_use") {
      addAgentLog("coordinator", `委派工具：${event.tool || event.name || "未知工具"}`);
    } else if (event.kind === "agent_error") {
      setAgentState(agent, "error", "失敗");
      addAgentLog(agent, event.error || "執行失敗");
    }
  }

  function renderAgentResult(event) {
    const payload = event.payload || {};
    const blocks = [];
    const summary = String(event.summary || payload.coordinator_summary || "").trim();
    const analysis = String(payload.analyst_summary || "").trim();
    const advice = String(payload.user_city_advice || "").trim();
    if (summary) blocks.push(["協調者總結", summary]);
    if (analysis) blocks.push(["分析師摘要", analysis]);
    if (advice) blocks.push(["個人行動建議", advice]);
    const result = $("agent-result");
    if (!blocks.length) {
      blocks.push(["流程結果", "資料採集已完成；後端未啟用 LLM 時，分析師與顧問會誠實標示為已略過。"]);
    }
    result.innerHTML = blocks.map(([title, text]) => `<article class="agent-block"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p></article>`).join("");
    result.hidden = false;
  }

  async function processSse(response) {
    if (!response.body) throw new Error("瀏覽器不支援串流回應");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const chunks = buffer.split(/\r?\n\r?\n/);
      buffer = chunks.pop() || "";
      for (const chunk of chunks) {
        const data = chunk.split(/\r?\n/)
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim())
          .join("\n");
        if (!data) continue;
        let event;
        try { event = JSON.parse(data); } catch (_) { continue; }
        if (event.kind === "error") throw new Error(event.error || "Agent 流程失敗");
        if (event.kind === "done") {
          setAgentState("coordinator", "done", "完成");
          if (event.payload?.cities?.length) {
            state.latest = validateLatest(event.payload);
            const ids = new Set(state.latest.cities.map((city) => city.city_id));
            if (!ids.has(state.selectedCity)) state.selectedCity = state.latest.cities[0].city_id;
            renderAll();
          }
          renderAgentResult(event);
          addAgentLog("coordinator", "流程與資料更新完成");
        } else {
          handleAgentEvent(event);
        }
      }
      if (done) break;
    }
  }

  async function runAgents() {
    if (!state.backendOnline || state.runningAgents) return;
    resetAgentFlow();
    state.runningAgents = true;
    $("agent-flow").setAttribute("aria-busy", "true");
    setAgentState("coordinator", "running", "協調中");
    addAgentLog("coordinator", "建立本次分析工作流");
    updateBackendUI();
    try {
      const response = await fetch(apiUrl("/api/coordinator/stream"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
        body: JSON.stringify({ profile: backendProfile(), city: state.selectedCity, llm: null }),
      });
      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
          const body = await response.json();
          message = body.detail || body.error || message;
        } catch (_) {}
        throw new Error(message);
      }
      await processSse(response);
      state.history = await fetchJson(apiUrl("/api/history")).catch(() => state.history);
      renderTrend();
      renderCompare();
    } catch (error) {
      setAgentState("coordinator", "error", "失敗");
      addAgentLog("coordinator", error.message || "Agent 流程失敗");
      showToast(`Agent 流程失敗：${error.message}`);
    } finally {
      state.runningAgents = false;
      $("agent-flow").setAttribute("aria-busy", "false");
      updateBackendUI();
    }
  }

  function openChat() {
    $("chat-panel").hidden = false;
    $("chat-fab").setAttribute("aria-expanded", "true");
    requestAnimationFrame(() => $("chat-text").focus());
  }

  function closeChat() {
    $("chat-panel").hidden = true;
    $("chat-fab").setAttribute("aria-expanded", "false");
    $("chat-fab").focus();
  }

  function appendChat(role, text, refs = []) {
    const message = document.createElement("div");
    message.className = `chat-msg ${role}`;
    const copy = document.createElement("span");
    copy.className = "txt";
    copy.textContent = text;
    message.append(copy);
    if (refs.length) {
      const reference = document.createElement("div");
      reference.className = "refs";
      reference.textContent = `參考：${refs.map((item) => item.source).filter(Boolean).join("、")}`;
      message.append(reference);
    }
    $("chat-body").append(message);
    $("chat-body").scrollTop = $("chat-body").scrollHeight;
  }

  async function sendChat(event) {
    event.preventDefault();
    const input = $("chat-text");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    appendChat("user", message);
    if (!state.backendOnline) {
      const city = cityById(state.selectedCity);
      const limitation = state.latest?.data_mode === "real" && (sourceAgeMinutes() ?? 999) <= 120
        ? ""
        : " 但目前是展示或過期資料，不能當成即時判斷。";
      appendChat("bot", city ? `目前未連上分析後端。畫面快照中的${city.city} AQI 是 ${numberText(city.aqi, 0)}（${aqiInfo(city.aqi).level}）。${limitation}` : "目前未連上分析後端，也沒有可用城市資料。");
      return;
    }
    input.disabled = true;
    try {
      const response = await fetchJson(apiUrl("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, profile: backendProfile(), llm: null }),
      }, 45000);
      appendChat("bot", String(response.answer || "後端沒有回覆內容"), Array.isArray(response.refs) ? response.refs : []);
    } catch (error) {
      appendChat("bot", `無法取得回答：${error.message}`);
    } finally {
      input.disabled = false;
      input.focus();
    }
  }

  function bindEvents() {
    $("settings-btn").addEventListener("click", openSettings);
    $("set-backend").addEventListener("click", openSettings);
    $("sidebar-close").addEventListener("click", closeSettings);
    $("sidebar-backdrop").addEventListener("click", closeSettings);
    $("sidebar").addEventListener("keydown", trapSidebarFocus);
    $("settings-form").addEventListener("submit", saveSettings);
    $("settings-reset").addEventListener("click", resetSettings);
    $("set-threshold").addEventListener("input", (event) => { $("set-thr-val").textContent = event.target.value; });
    $("theme-toggle").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"));
    $("home-city-select").addEventListener("change", (event) => selectCity(event.target.value, { saveHome: true }));
    $("city-select").addEventListener("change", (event) => selectCity(event.target.value));
    $("city-search").addEventListener("input", renderCityGrid);
    $("region-filter").addEventListener("change", renderCityGrid);
    $("sort-select").addEventListener("change", renderCityGrid);
    $("city-grid").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      if (button.dataset.action === "compare") toggleCompare(button.dataset.city);
      else selectCity(button.dataset.city, { scroll: true });
    });
    $("compare-clear").addEventListener("click", () => {
      state.compareCities = [];
      renderCityGrid();
      renderCompare();
    });
    $("trend-range").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-hours]");
      if (!button) return;
      state.trendHours = Number(button.dataset.hours);
      for (const item of $("trend-range").querySelectorAll("button")) item.classList.toggle("active", item === button);
      renderTrend();
      renderCompare();
    });
    $("run-agents").addEventListener("click", runAgents);
    $("chat-fab").addEventListener("click", openChat);
    $("chat-close").addEventListener("click", closeChat);
    $("chat-form").addEventListener("submit", sendChat);
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!$("sidebar").hidden) closeSettings();
      else if (!$("chat-panel").hidden) closeChat();
    });
    window.addEventListener("plotly-ready", () => {
      state.rankingBound = false;
      if (state.latest) {
        renderRanking();
        renderTrend();
        renderCompare();
      }
    });
  }

  async function boot() {
    bindEvents();
    resetAgentFlow();
    const savedTheme = readTextStorage(STORAGE.theme, document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
    applyTheme(savedTheme);
    try {
      await loadData(false);
    } catch (error) {
      showLoadError(error);
    }
    await checkBackend();
    if (state.backendOnline) {
      try { await loadData(true); } catch (_) {}
    }
    setInterval(() => state.latest && renderDataStatus(), 60000);
    setInterval(async () => {
      try {
        if (state.backend) await checkBackend();
        await loadData(state.backendOnline);
      } catch (_) {}
    }, 10 * 60 * 1000);
  }

  boot();
})();
