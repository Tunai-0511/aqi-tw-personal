# Hermes、Discord 部署指南

這一版包含可操作的整合中心、Supabase 身分驗證、Discord OAuth、Hermes Profile 佈建器，以及網站 → Hermes API 訊息轉送。

## 1. 先用本機示範模式測試 UI

PowerShell：

```powershell
$env:INTEGRATION_DEV_MODE = "1"
$env:INTEGRATION_STATE_SECRET = "local-test-secret-change-this-123456"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

另一個終端：

```powershell
python -m http.server 8801 --directory docs
```

開啟 `http://127.0.0.1:8801/integrations.html`。輸入測試使用者後，可以模擬 Discord 綁定。示範資料只放在後端記憶體，重啟後會清除。

## 2. Supabase

AgentAQI 必須使用獨立的 Supabase Project，不可與 IPAS 或其他正式服務共用資料庫。

1. 在 Supabase SQL Editor 執行 `supabase/schema.sql`。
2. Authentication → URL Configuration：
   - Site URL：正式 Cloudflare 網域。
   - Redirect URLs：加入正式網域的 `/integrations.html` 與本機測試網址。
3. Project Settings → API 取得 Project URL、anon key、service role key。
4. 複製 `.env.example` 為 `.env`，填入三個 Supabase 值。

`SUPABASE_SERVICE_ROLE_KEY` 只能存在後端環境變數，不可放進 `docs/`、GitHub Pages 或前端 JavaScript。

## 3. Hermes Docker

```powershell
Copy-Item .env.hermes.example .env.hermes
docker compose -f docker-compose.hermes.yml up -d
docker exec hermes hermes doctor
```

先在 Hermes 預設 Profile 設定模型供應商；`.env.hermes` 的 `API_SERVER_KEY` 必須與後端 `.env` 的 `HERMES_API_KEY` 相同。

啟用自動 Profile 佈建：

```dotenv
HERMES_PROVISION_MODE=docker
HERMES_CONTAINER=hermes
HERMES_API_URL=http://127.0.0.1:8642
HERMES_API_KEY=與.env.hermes相同的值
```

後端主機必須能執行 Docker CLI。公開部署時不要把 Docker socket 暴露給網際網路，也不要讓 Hermes API 的 `8642` 直接對外公開。

## 4. Discord

1. 在 Discord Developer Portal 建立 Application 與 Bot。
2. OAuth2 Redirect URI 設為：
   `https://你的後端網域/api/integrations/discord/callback`
3. 後端設定：

```dotenv
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DISCORD_REDIRECT_URI=https://你的後端網域/api/integrations/discord/callback
```

4. Hermes `.env.hermes` 設定 `DISCORD_BOT_TOKEN`。

目前採中央 Discord Bot。Hermes Gateway 負責 Discord 即時訊息；網站負責 OAuth 安裝、Supabase 綁定和 Profile 佈建。公開服務應使用明確的允許頻道／角色規則，不要在含終端工具的 Agent 上無限制開啟 `DISCORD_ALLOW_ALL_USERS`。

## 5. 正式環境最低安全設定

- `INTEGRATION_DEV_MODE=0`
- `AQI_CORS` 只列出正式前端網域
- `INTEGRATION_STATE_SECRET` 使用至少 32 個隨機字元
- Supabase RLS 保持啟用
- 後端與 Hermes API 僅走內網
- 對 OAuth 與 Hermes chat 端點加入反向代理 rate limit
- 生產環境固定 Hermes Docker image 版本，不長期使用 `latest`
