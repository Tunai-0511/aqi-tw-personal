# Secrets & OAuth

## 三個 secret 檔

```
C:\Users\User\.openclaw\secrets\
├── google-cal.json          # 唯讀
├── google-cal-write.json    # 寫入（選用，要批次新增才需要）
└── moenv.json               # 環境部 AQI API key
```

### google-cal.json（read-only）

Scope: `https://www.googleapis.com/auth/calendar.readonly`

| Key | 用途 |
|---|---|
| `client_id` | GCP OAuth client id（Desktop app type） |
| `client_secret` | GCP OAuth client secret |
| `refresh_token` | 唯讀 refresh token |
| `token_uri` | 通常 `https://oauth2.googleapis.com/token` |
| `scopes` | list，含 `calendar.readonly` |

**用途**：
- `scripts/calendar-mcp-server.py` — MCP server
- `scripts/cal_env_watch.py` — 讀行程

⚠️ **不要在這檔加 write scope**，會破壞現有 MCP server 設定。

### google-cal-write.json（write）

Scope: `https://www.googleapis.com/auth/calendar.events`

由 `scripts/oauth_calendar_write.py` 一次性建立，**結構跟 google-cal.json
一樣**（同 client_id/secret，refresh_token 是新的有 write 權限的那個）。

**用途**：
- `scripts/insert_class_schedule.py` — 批次新增
- 未來任何 insert/modify script

### moenv.json（環境部 AQI）

```json
{
  "moenv_api_key": "..."
}
```

**注意**：Moenv key 不在 OpenClaw 內建 credential surface，所以沒有 SecretRef 直
接引用。腳本都是直接 `json.loads(MOENV_SECRETS_PATH.read_text())` 讀檔。

API endpoint:
```
https://data.moenv.gov.tw/api/v2/aqx_p_432?api_key={key}&limit=1000&format=JSON
```

## 換 write scope 的 OAuth 流程

適用情境：第一次要批次新增 event，或 read-only 已經過期。

```powershell
python scripts\oauth_calendar_write.py
```

1. 用 `google-cal.json` 的 `client_id` / `client_secret` 建立 InstalledAppFlow
2. 開瀏覽器到 Google consent screen
3. 登入 → 看到 "Allow openclaw to **make changes to events**?" → Allow
4. 程式把新 refresh_token + 同樣的 client_id/secret 寫到
   `google-cal-write.json`
5. 鎖檔案 ACL（`icacls /inheritance:r` + Administrators/SYSTEM/目前使用者 full）

**重要**：`prompt="consent"` 強制要 consent screen，這樣 Google 才會發
refresh_token（否則只給 access_token，下次還要登入）。

## Token 過期怎麼辦

- **Access token** (1hr): script 自動用 refresh_token 換新的，不用管
- **Refresh token** (永久，除非 revoke):
  - 換了 OAuth client secret → 要重跑 `oauth_calendar_write.py`
  - User 在 Google 帳號手動 revoke → 要重跑
  - 太久沒用 (Google 6 個月 policy) → 要重跑

## 鎖檔案 ACL

```powershell
icacls "C:\Users\User\.openclaw\secrets\google-cal-write.json" /inheritance:r
icacls "C:\Users\User\.openclaw\secrets\google-cal-write.json" /grant:r "$env:USERNAME:F" "SYSTEM:F" "Administrators:F"
```

`oauth_calendar_write.py` 會自動跑這段（best-effort，失敗不擋）。
