# 🦞 LobsterAQI — 台灣空氣品質多代理人監控平台

深色科技風 SaaS 監控介面。三個 agent（採集者 → 分析師 → 預警員）接力採集、分析、預警台灣 20 個縣市（含離島）的空氣品質。

LobsterAQI 兩件事是分開的：

| 元件 | 角色 | 必填？ |
|------|------|--------|
| **直接 LLM API**（Anthropic / Gemini / MiniMax / OpenAI / 自訂） | Pipeline 中分析師 + 預警員的 LLM 呼叫 + 右下角 AI 助理 + 城市比較頁 AI 比較 | ⭐ 必填一個 |
| **EPA Open Data Token**（環境部資料開放平臺） | 拉取 20 縣市即時 AQI | ⭐ 必填 |
| **OpenClaw**（自架 lobster gateway） | 排程推送 Discord/LINE、個人記憶、進階 RAG | 選填（沒裝也可全功能跑） |

---

## 🚀 快速啟動（Windows）

### Step 1：跑起來

```
解壓 zip → 雙擊 run.bat → 等 1-2 分鐘自動裝依賴 → 瀏覽器自動開啟
```

`run.bat` 會：
1. 偵測 Python（沒裝會引導去 [python.org](https://www.python.org/downloads/) 下載）
2. 首次啟動建立 `.venv` + `pip install -r requirements.txt`
3. 之後直接 activate venv → 啟動 Streamlit
4. 自動打開 `http://localhost:8501`

### Step 2：填兩個金鑰（必填）

打開後 sidebar 上有：

**A. LLM 提供商**
- 選一個提供商（Anthropic / Google Gemini / MiniMax / OpenAI / 自訂）
- 貼上你的 API Key
- ✓ 綠 pill「{Provider} · 金鑰已填」= OK

**B. EPA Open Data Token**
- 申請：登入 [環境部資料開放平臺](https://data.moenv.gov.tw/) → 個人專區 → API 金鑰
- 貼進 sidebar 的「EPA Token」欄
- 按「🔌 測試 EPA Token」確認 → 綠燈「✓ Token 有效 · 取得 N 測站」

### Step 3：啟動 Pipeline

封面點「▶ 啟動三代理人 Pipeline」→ smooth scroll 到劇場區 → 3 個 agent 依序亮起跑分析（~10-30 秒）→ 主儀表板出來。

### Step 4（選填）：Discord 推送

Sidebar 「Discord 推送」貼一條 channel webhook URL（頻道設定 → 整合 → Webhook → 複製 URL），按「🧪 測試 Discord」確認可用。之後 Pipeline 跑完會自動 POST 全國 AQI 摘要 + 最高/最低城市到該頻道。

---

## 📡 資料來源（全部為真實外部 API，無合成資料）

| 用途 | 來源 | API | 需金鑰 |
|------|------|-----|--------|
| 即時 AQI（官方） | 環境部 EPA | `data.moenv.gov.tw/api/v2/aqx_p_432` | ✓ 你的 api_key |
| 24h 歷史 AQI（官方） | 環境部 EPA | `data.moenv.gov.tw/api/v2/aqx_p_488` | ✓ 同上 |
| 民間 PM2.5 即時（主要） | 民生公共物聯網 · 智慧城鄉空品微型感測器 | `sta.colife.org.tw/STA_AirQuality_EPAIoT/v1.0/`（OGC SensorThings API）| ✗ 公開 |
| 民間 PM2.5 即時（補充） | LASS-net Airbox 社群網路 | `pm25.lass-net.org/data/last-all-airbox.json` | ✗ 公開 |
| 24h 歷史 + 6h 預測（模型） | Open-Meteo · Copernicus CAMS | `air-quality-api.open-meteo.com/v1/air-quality` | ✗ 公開 |
| 氣象（溫濕度、風向、氣壓） | Open-Meteo | `api.open-meteo.com/v1/forecast` | ✗ 公開 |
| LLM 分析 | Anthropic / MiniMax / DeepSeek / OpenAI / 自訂 | 各自的 `/chat/completions` 或 `/v1/messages` | ✓ 你的 LLM key |
| 本機時序快取 | SQLite | `./lobster_aqi.sqlite` | ✗ 純本機 |
| Pipeline 推送 | Discord Channel Webhook | `discord.com/api/webhooks/...` | ✓ 你的 webhook URL |

---

## 🦞 3 個 agent 接力 pipeline

| 內部 ID | UI 顯示 | 用 LLM？ | 工作 | 資料源 |
|---------|---------|--------|------|--------|
| `collector` | **採集者** | ❌ 純 ETL | EPA 即時抓取 + Open-Meteo 氣象 + 民生公共物聯網 / LASS 並行清洗 | 環境部 EPA `aqx_p_432` + Open-Meteo + 民生公共物聯網 SensorThings + LASS-net Airbox |
| `analyst`   | **分析師** | ✅ | 整合資料 + RAG 文獻檢索，產出 3 段風險分析（現況 / 敏感族群 / 未來 6h 研判）| 採集者輸出 + RAG（WHO 2021 / EPA NAAQS / Lancet 2023 / 台灣 AQI 標準）|
| `advisor`   | **預警員** | ✅ | 接分析師的風險分級，產出 5 類敏感族群（老人 / 幼童 / 氣喘 / 心血管 / 孕婦）的具體建議 | 上方資料 |

**為何只剩 3 個？**

初版設計過於追求「multi-agent」概念塞了 5 個 agent（採集者、爬蟲員、分析師、品管員 Critic、預警員），但其中 3 個的 LLM 呼叫只是「對剛跑完的 Python 程式碼寫一句註解」，沒有實際進入下游分析。Critic 的 0-100 分也沒實際 gate 任何重試。3-agent 重構把 ETL 集中在採集者（純資料處理、無 LLM），讓 LLM 只用在它擅長的「分析」與「個人化建議」兩個環節。`scraper/` 與 `critic/` 兩個 agent 工作區也於 2026-05-13 一併刪除。

`analyst` 與 `advisor` 用**同一個** LLM 提供商（你在 sidebar 選的那個）。Anthropic / Google Gemini / MiniMax / OpenAI / 自訂都可以。

---

## 📑 單頁結構（10 個 SECTION）

LobsterAQI 是 Streamlit 單頁應用 — 從封面捲到底,依序為 10 個 SECTION:

| SECTION | 內容 |
|---------|------|
| 封面 | LobsterAQI 品牌標題 + 「啟動三代理人 Pipeline」按鈕 + 狀態指示 |
| 01 三隻 agent 協作 | 像素風辦公室 + 3 個 agent 群組聊天室 |
| 02 即時 AQI 主儀表板 | 時間軸 scrubber + 聚焦城市 + 排名 + 地圖 + 散點 + 新鮮度燈號 |
| 03 24 小時趨勢 | 多城市 AQI 趨勢線 |
| 04 污染物剖析 | 熱力圖 + 雷達圖 + 堆疊組成 + PM2.5 vs AQI 散點 |
| 05 環境關聯 | 濕度 vs PM2.5、風玫瑰 |
| 06 官方 vs 民間 | EPA 測站對比 CivilIoT / LASS-net 微型感測器 |
| 07 健康預警 | 每個城市一張預警卡,點敏感族群篩選建議 |
| 08 個人化推薦 | 你的常駐城市 + 健康狀況 → 個人化健康指數卡 + 7 天趨勢 |
| 09 健康日誌 | 每日打卡(症狀分數 + 戶外時數)+ 症狀 vs AQI 相關性散點 |
| 10 個人訂閱 | 表單產生 OpenClaw cron 指令,推播到 Discord(支援每日 Digest 模式)|

主儀表板上方有**時間軸 scrubber** — 拖動可看過去 24h 任一時點的快照。主畫面點「🔍 查看 [city] 詳細」會開啟**城市深入 modal**(無頁面切換,捲動位置保留),內容由 `_city_detail.py` 共用。

右下角有**浮動 AI 助理 FAB**(LINE 風格聊天視窗),整合 RAG + LLM 回答空品相關問題。

---

## 🔌 進階：OpenClaw 整合（選填）

LobsterAQI 主功能不需要 OpenClaw，但加上後可以：
- 排程每小時推播 AQI 摘要到 Discord
- 把分析師綁到 Discord 頻道（@分析師 直接問空品）
- 持久化使用者個人健康記憶（agent 跨 session 記得你）
- 真實 RAG 文獻檢索（取代寫死的 snippets）

### A. 安裝 OpenClaw（Windows + WSL2 推薦）

```powershell
# 1. PowerShell（管理員）
wsl --install -d Ubuntu
# 重開機
```

```bash
# 2. Ubuntu 內
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g openclaw
openclaw onboard --install-daemon
```

完整指南：[OpenClaw Getting Started](https://docs.openclaw.ai/start/getting-started)

### B. 註冊 3 個 agents（與 LobsterAQI 期待的 ID 一致）

從專案根目錄：
```bash
for id in collector analyst advisor; do
  openclaw agents add "$id" --workspace "./openclaw_agents/$id" \
    --model minimax/MiniMax-M2.7 --non-interactive --json
done
```

每個 agent 的 `openclaw_agents/<id>/SOUL.md` + `IDENTITY.md` 已預先客製。
（早期 5-agent 設計的 `scraper/` 與 `critic/` 兩個工作區已於 2026-05-13 移除,
3-agent 重構後不再使用。）

### C. 排程推送 Discord（每小時 AQI 摘要）

```bash
scripts\setup_cron.bat       # 互動式輸入 Discord 頻道 ID
```

或手動：
```bash
openclaw cron add --name "TW-AQI-hourly" --cron "0 * * * *" --tz "Asia/Taipei" ^
  --session isolated --agent analyst ^
  --message "請拉取台灣即時 AQI 並用 3 段繁體中文摘要..." ^
  --announce --channel discord --to "channel:<YOUR_CHANNEL_ID>"
```

查看 / 修改 / 刪除：
```bash
openclaw cron list
openclaw cron edit TW-AQI-hourly
openclaw cron remove TW-AQI-hourly
openclaw cron run TW-AQI-hourly       # 立即跑一次測試
```

### D. Discord / LINE 雙向助理（在 Discord @ 分析師問空品）

**Discord 5 步驟**：
1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 開 Bot，記下 token
2. `openclaw configure` → Discord → 貼 token
3. 把 Bot 邀請到你的 Discord server
4. `openclaw pairing approve discord <code>`
5. `openclaw agents bind --agent analyst --bind discord:<channel-id>`

**LINE**：OpenClaw 2026.x 對 LINE 支援還在實驗階段，文件不全，可能需要等版本更新。

### E. 個人健康記憶

主畫面「個人化推薦」section 填好城市/狀況後，按「💾 同步至 OpenClaw 記憶體」。會寫進：
- `~/.openclaw/agents/analyst/agent/MEMORY.md`
- `~/.openclaw/agents/advisor/agent/MEMORY.md`

下次經由 Discord / LINE 對話時，agent 會自動帶上你的背景。

### F. 個人閾值訂閱

主畫面捲到底部 SECTION · 10「個人訂閱」→ 填表單 → 自動產生 `openclaw cron add` 指令。例：「我住高雄、氣喘、AQI > 80 時推到 Discord」→ 每小時自動跑 → 條件成立才送。支援兩種推送模式:

- **📅 每日 Digest** — 每天固定時段推完整摘要(空品速覽 + 預測 + 族群建議 + 警示時段)
- **⚠ 即時預警** — 只在 AQI 突破閾值時推單條警示

### G. 正式 RAG 知識庫

預設的 RAG 引用是寫死的 4 條 snippets。要換成真實檢索：

```bash
# 1. 下載 WHO 2021 PDF + EPA NAAQS + 台灣 AQI 標準 + Lancet 2023
scripts\build_knowledge.bat

# 2. 安裝到 OpenClaw skill
robocopy openclaw_skills\aqi-knowledge ^
  %USERPROFILE%\.openclaw\workspace\skills\aqi-knowledge /E

# 3. 重建索引
openclaw memory reindex --skill aqi-knowledge
```

詳細文獻清單與授權見 [`docs/knowledge_sources.md`](docs/knowledge_sources.md)。

---

## 🏗 架構

```
┌──────────────────────────────────────────────────────────────┐
│                        使用者瀏覽器                            │
└────────────────────────┬─────────────────────────────────────┘
                         │ localhost:8501
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  LobsterAQI Streamlit                                         │
│  - 封面 / 劇場 / 10 個 SECTION(02-10 主要儀表板區)             │
│  - 群組聊天室 + 右下角 AI 助理 + 城市深入 modal                 │
│  - 時間軸 scrubber + 健康日誌 + 個人訂閱表單                    │
└──┬───────────────────────────────────────────────────────────┘
   │
   ├──── HTTP ────► data.moenv.gov.tw           (環境部 EPA 即時 aqx_p_432 + 歷史 aqx_p_488)
   ├──── HTTP ────► sta.colife.org.tw           (民生公共物聯網 SensorThings · 智慧城鄉空品微型感測器)
   ├──── HTTP ────► pm25.lass-net.org           (LASS-net Airbox 社群網路 · 補充離島)
   ├──── HTTP ────► api.open-meteo.com          (氣象，免金鑰)
   ├──── HTTP ────► air-quality-api.open-meteo  (CAMS 大氣化學模式，免金鑰)
   ├──── HTTP ────► Anthropic / MiniMax / DeepSeek / OpenAI / 自訂
   │                 (sidebar 選的 LLM 提供商；in-app 即時回應)
   ├──── HTTP ────► discord.com/api/webhooks/…  (選填；Pipeline 完成推播摘要)
   │
   ├──── SQLite ──► ./lobster_aqi.sqlite        (本機時序快取 + 健康日誌；跨重啟保留)
   └──── shell ──► scripts/setup_cron.bat ──► openclaw cron
                          (選填；用於排程推送、MEMORY 寫入。
                           OpenClaw gateway 跑在 localhost:18789,
                           處理排程、Discord/LINE 路由;in-app LLM 不走它)
```

**為什麼這樣切？** OpenClaw gateway 第一次冷啟動要 30-60 秒（plugin 探測），不適合放在「使用者點按鈕等回應」這條路徑上。但它的 cron + channel 系統很強，適合放在「使用者不在 LobsterAQI 也能收到推播」這條路徑上。

---

## 🔧 故障排除

| 症狀 | 處理 |
|------|------|
| `run.bat` 跳 `Python not found` | 裝 Python 3.10+，記得勾「Add Python to PATH」 |
| `pip install` 紅字 | 檢查網路；公司網路擋外部時加 `--index-url` 用內部鏡像 |
| `ImportError: cannot import name 'LLM_PROVIDERS'` | Streamlit 進程有舊版 `data` 模組快取。Ctrl+C 終止 → `run.bat` 重跑（不是 menu 的 Rerun）|
| EPA「失敗：TOKEN 無效 / 速率限制」 | 用 sidebar 的「🔌 測試 EPA Token」看伺服器原始錯誤；常見：token 複製時漏字 |
| EPA「JSON 解出但找不到 records · 結構：...」 | MOENV 又改 schema。請貼錯誤訊息給 dev 補 `_resolve_col` |
| Pipeline 跑完 LLM 評論段是空的 | sidebar 沒填 LLM key；填了再啟動一次 |
| 「OpenClaw cron list」啥都沒有 | 還沒跑 setup_cron.bat 或 openclaw onboard，那是進階功能 |
| Port 8501 被佔 | 改 `.streamlit/config.toml` 的 `server.port` |

---

## 📁 檔案結構

```
aqi-tw-personal-main/
├── app.py                  # Streamlit 主入口（封面 + 10 個 SECTION + 城市深入 modal + AI 助理）
├── data.py                 # EPA / Open-Meteo / CivilIoT / LASS fetcher + LLM_PROVIDERS + call_llm_api
├── tsdb.py                 # SQLite 本機時序快取(aqi_snapshots / cams_hourly / health_diary)
├── charts.py               # Plotly 圖表工廠
├── styles.py               # 深色主題 CSS
├── _city_detail.py         # 城市深入 modal 共用渲染(底線前綴避免被 Streamlit pages 探索)
├── openclaw_agents/        # 3 個 agent 的 SOUL.md / IDENTITY.md（給 OpenClaw 進階用）
│   ├── advisor/            # 預警員
│   ├── analyst/            # 分析師
│   └── collector/          # 採集者
├── openclaw_skills/
│   └── aqi-knowledge/      # SKILL.md +（跑 scripts/build_knowledge.bat 後填入 PDF）
├── scripts/
│   ├── build_knowledge.bat # 下載 WHO/EPA/Lancet 文獻
│   └── setup_cron.bat      # 註冊 OpenClaw 排程
├── docs/
│   └── knowledge_sources.md
├── CHANGELOG.md            # 變更紀錄
├── .gitignore
├── .streamlit/config.toml
├── requirements.txt
├── run.bat                 # Windows 雙擊啟動器
└── README.md
```

---

## 🎨 設計備註

- **配色**：bg `#04060f`、cyan `#00d9ff`、orange `#ff8c42`、green `#00e676`、yellow `#ffd93d`、red `#ff4757`、purple `#9b59ff`
- **字型**：Inter（介面）+ JetBrains Mono（數字 / tooltip）
- **群組聊天室**：通訊日誌做成 Slack 風格 chat，顯示「誰對誰講話 / 誰給誰資料」
- **右下角浮動 AI 助理**：純 CSS fixed-position 面板（不是 modal），可一邊聊一邊滑頁面
- **封面頁**：第一次進入是大型 hero + 一鍵啟動，所有資料 section gate 在啟動之後

---

## 🦞 為什麼叫 LobsterAQI

致敬 [OpenClaw](https://github.com/openclaw/openclaw) 的 lobster 🦞 主題。即使現在的核心 LLM 路徑不走 OpenClaw，視覺主題與進階推送功能仍保留龍蝦概念。
