import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

const $ = (id) => document.getElementById(id);
const state = { config: null, supabase: null, session: null, demoUser: "", integrations: {} };
let toastTimer;

function backendUrl() {
  const query = new URLSearchParams(location.search).get("api");
  let saved = "";
  try { saved = localStorage.getItem("aqi_backend") || ""; } catch (_) {}
  const local = ["localhost", "127.0.0.1"].includes(location.hostname) ? "http://127.0.0.1:8000" : "";
  return String(query || saved || local).trim().replace(/\/+$/, "");
}

function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3600);
}

function headers() {
  if (state.session?.access_token) return { Authorization: `Bearer ${state.session.access_token}` };
  if (state.demoUser) return { "X-Demo-User": state.demoUser };
  return {};
}

async function api(path, options = {}) {
  const base = backendUrl();
  if (!base) throw new Error("請先設定 FastAPI 網址");
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...headers(), ...(options.headers || {}) },
  });
  let body = {};
  try { body = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body;
}

function setServiceStatus(text, online = false) {
  $("service-status").textContent = text;
  $("service-status").classList.toggle("online", online);
}

function renderAuth() {
  const signedIn = Boolean(state.session || state.demoUser);
  $("magic-form").hidden = signedIn || !state.config?.auth_enabled;
  $("demo-form").hidden = signedIn || !state.config?.dev_mode;
  $("signed-user").hidden = !signedIn;
  $("sign-out").hidden = !signedIn;
  $("connect-section").hidden = !signedIn;
  if (signedIn) {
    const label = state.session?.user?.email || `${state.demoUser}（本機測試）`;
    $("user-label").textContent = label;
    $("user-avatar").textContent = label.slice(0, 1).toUpperCase();
    $("auth-title").textContent = "帳號已連接";
    $("auth-description").textContent = "現在可以管理平台綁定與 Hermes Agent 狀態。";
  } else {
    $("auth-title").textContent = "先確認你的身分";
    $("auth-description").textContent = state.config?.dev_mode
      ? "目前開啟本機示範模式，也可以測試完整操作流程。"
      : "平台連線與 Agent 記憶會綁定到你的 Supabase 帳號。";
  }
}

function renderPlatform(platform) {
  const item = state.integrations[platform];
  const stateEl = $(`${platform}-state`);
  const detail = $(`${platform}-detail`);
  const button = $(`${platform}-action`);
  stateEl.className = "platform-state";
  if (!item) {
    stateEl.textContent = "未連接";
    detail.textContent = "需要 Discord OAuth 與中央 Bot。";
    button.textContent = "連接 Discord";
    button.dataset.mode = "connect";
    return;
  }
  const labels = { connected: "已綁定", provisioning: "佈建中", ready: "Profile 已建立", error: "需要處理" };
  stateEl.textContent = labels[item.status] || item.status;
  stateEl.classList.add(item.status === "ready" ? "ready" : item.status === "error" ? "error" : "working");
  detail.textContent = [item.platform_user_name, item.platform_space_name, item.provision_detail].filter(Boolean).join(" · ") || "平台已連接";
  button.textContent = item.status === "error" ? "重試 Hermes 佈建" : "解除連接";
  button.dataset.mode = item.status === "error" ? "retry" : "disconnect";
}

function renderPlatforms() { renderPlatform("discord"); }

async function loadIntegrations() {
  if (!state.session && !state.demoUser) return;
  const result = await api("/api/integrations");
  state.integrations = result.integrations || {};
  renderPlatforms();
}

async function loadConfig() {
  $("backend-url").value = backendUrl();
  try {
    state.config = await api("/api/integrations/config");
    setServiceStatus(state.config.hermes_mode === "disabled" ? "整合 API 已連線" : `Hermes：${state.config.hermes_mode}`, true);
    $("setup-notice").hidden = state.config.enabled;
    if (!state.config.enabled) $("setup-message").textContent = "請先執行 Supabase SQL 並設定後端環境變數。";
  } catch (error) {
    setServiceStatus("後端未連線");
    $("setup-notice").hidden = false;
    $("setup-message").textContent = error.message;
    state.config = { enabled: false, auth_enabled: false, dev_mode: false };
  }

  if (state.config.auth_enabled) {
    state.supabase = createClient(state.config.supabase_url, state.config.supabase_anon_key);
    const { data } = await state.supabase.auth.getSession();
    state.session = data.session;
    state.supabase.auth.onAuthStateChange((_event, session) => {
      state.session = session;
      renderAuth();
      if (session) loadIntegrations().catch((error) => toast(error.message));
    });
  }
  renderAuth();
  if (state.session) await loadIntegrations();
}

async function connectDiscord() {
  const button = $("discord-action");
  const mode = button.dataset.mode || "connect";
  if (mode === "disconnect") return disconnect("discord");
  if (mode === "retry") return retry("discord");
  button.disabled = true;
  try {
    if (!state.config.discord_enabled && state.config.dev_mode) {
      await api("/api/integrations/discord/demo-connect", { method: "POST" });
      await loadIntegrations();
      toast("Discord 示範綁定完成");
      return;
    }
    const result = await api("/api/integrations/discord/connect", { method: "POST" });
    location.href = result.authorization_url;
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
}

async function disconnect(platform) {
  if (!confirm("確定解除 Discord 綁定？")) return;
  try {
    await api(`/api/integrations/${platform}`, { method: "DELETE" });
    delete state.integrations[platform];
    renderPlatforms();
    toast("平台連接已解除");
  } catch (error) { toast(error.message); }
}

async function retry(platform) {
  try {
    await api(`/api/integrations/${platform}/provision`, { method: "POST" });
    await loadIntegrations();
    toast("已重新送出 Hermes 佈建工作");
  } catch (error) { toast(error.message); }
}

function bindEvents() {
  $("backend-form").addEventListener("submit", (event) => {
    event.preventDefault();
    try { localStorage.setItem("aqi_backend", $("backend-url").value.trim().replace(/\/+$/, "")); } catch (_) {}
    location.reload();
  });
  $("magic-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = $("auth-email").value.trim();
    const { error } = await state.supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: location.href.split("?")[0] } });
    toast(error ? error.message : "登入連結已寄出，請檢查信箱");
  });
  $("demo-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.demoUser = $("demo-user").value.trim();
    try { sessionStorage.setItem("aqi_demo_user", state.demoUser); } catch (_) {}
    renderAuth();
    try { await loadIntegrations(); } catch (error) { toast(error.message); }
  });
  $("sign-out").addEventListener("click", async () => {
    if (state.supabase && state.session) await state.supabase.auth.signOut();
    state.session = null; state.demoUser = ""; state.integrations = {};
    try { sessionStorage.removeItem("aqi_demo_user"); } catch (_) {}
    renderAuth(); renderPlatforms();
  });
  $("refresh-status").addEventListener("click", () => loadIntegrations().catch((error) => toast(error.message)));
  $("discord-action").addEventListener("click", connectDiscord);
}

async function boot() {
  try { state.demoUser = sessionStorage.getItem("aqi_demo_user") || ""; } catch (_) {}
  bindEvents();
  renderPlatforms();
  await loadConfig();
  const connected = new URLSearchParams(location.search).get("connected");
  if (connected === "discord") { toast("Discord 授權已完成"); history.replaceState({}, "", location.pathname); }
}

boot().catch((error) => { setServiceStatus("初始化失敗"); toast(error.message); });
