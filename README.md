# 🦞 LobsterAQI — 台灣空氣品質多代理人監控平台

深色科技風 SaaS 監控介面。四隻龍蝦代理人 + 一隻 Critic 協同採集、清洗、分析、預警台灣 20 個縣市（含離島）的空氣品質。

LobsterAQI 兩件事是分開的：

| 元件 | 角色 | 必填？ |
|------|------|--------|
| **直接 LLM API**（Anthropic / MiniMax / DeepSeek / OpenAI / 自訂） | Pipeline 中 5 隻 agent 的分析 + 右下角 AI 助理 + 城市比較頁 AI 比較 | ⭐ 必填一個 |
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
- 選一個提供商（Anthropic / MiniMax / DeepSeek / OpenAI / 自訂）
- 貼上你的 API Key
- ✓ 綠 pill「{Provider} · 金鑰已填」= OK

**B. EPA Open Data Token**
- 申請：登入 [環境部資料開放平臺](https://data.moenv.gov.tw/) → 個人專區 → API 金鑰
- 貼進 sidebar 的「EPA Token」欄
- 按「🔌 測試 EPA Token」確認 → 綠燈「✓ Token 有效 · 取得 N 測站」

### Step 3：啟動 Pipeline

封面點「▶ 啟動四代理人 Pipeline」→ smooth scroll 到劇場區 → 5 隻龍蝦依序亮起跑分析（~30-60 秒）→ 主儀表板出來。

---

## 🦞 5 隻龍蝦代理人

| 內部 ID | UI 顯示 | 任務 | 輸出 |
|---------|---------|------|------|
| `collector` | 採集者 | 評估剛抓到的 AQI 資料品質 | 1-2 句 |
| `scraper`   | 爬蟲員 | 評論民間感測器清洗結果 | 1 句 |
| `analyst`   | 分析師 | 3 段風險分析（現況/族群/趨勢）| 3 段 |
| `critic`    | 品管員 | 審分析師的報告，給 0-100 分 | 1 句 + 分數 |
| `advisor`   | 預警員 | 對 5 類敏感族群的具體建議 | 3-4 句 |

每隻 agent 用**同一個** LLM 提供商（你在 sidebar 選的那個）。Anthropic / MiniMax / DeepSeek / OpenAI 都可以。

---

## 📑 Multi-page 結構

左側 sidebar 自動顯示這 4 頁：

| 分頁 | 內容 |
|------|------|
| 主畫面 | 封面 + 龍蝦劇場 + 群組聊天室 + 主儀表板 |
| 1_城市深入 | 任一城市的詳細頁（6 種污染物 24h、6h 預測、最佳外出時段、健康建議）|
| 2_城市並排比較 | 2-3 城市同時比較（表格、雷達、24h 趨勢、AI 比較分析）|
| 3_個人訂閱 | 表單產生 OpenClaw cron 指令，推播到 Discord / Telegram |

主畫面點「🔍 查看 [city] 詳細」自動跳到城市深入頁。

主儀表板上方有**時間軸 scrubber** — 拖動可看過去 24h 任一時點的快照。

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

### B. 註冊 5 隻 agents（與 LobsterAQI 期待的 ID 一致）

從專案根目錄：
```bash
for id in collector scraper analyst critic advisor; do
  openclaw agents add "$id" --workspace "./openclaw_agents/$id" \
    --model minimax/MiniMax-M2.7 --non-interactive --json
done
```

每隻 agent 的 `openclaw_agents/<id>/SOUL.md` + `IDENTITY.md` 已預先客製。

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

進入「3_個人訂閱」分頁 → 填表單 → 自動產生 `openclaw cron add` 指令。例：「我住高雄、氣喘、AQI > 80 時推到 Discord」→ 每小時自動跑 → 條件成立才送。

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
│  - 封面 / 劇場 / 9 大儀表板 section                            │
│  - 群組聊天室 + 右下角 AI 助理 + 城市深入/比較 page             │
│  - 時間軸 scrubber                                            │
└──┬───────────────────────────────────────────────────────────┘
   │
   ├──── HTTP ────► data.moenv.gov.tw   (環境部 EPA API)
   ├──── HTTP ────► api.open-meteo.com  (氣象，免金鑰)
   ├──── HTTP ────► Anthropic / MiniMax / DeepSeek / OpenAI / 自訂
   │                 (sidebar 選的 LLM 提供商；in-app 即時回應)
   │
   └──── subprocess ────► openclaw CLI  (僅用於 cron 推送、MEMORY 寫入)
                          (OpenClaw gateway 跑在 localhost:18789，
                           處理排程、Discord/LINE 路由；in-app LLM 不走它)
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
aqi_dashboard/
├── app.py                  # Streamlit 主入口（封面 / 劇場 / 9 sections）
├── data.py                 # MOENV / Open-Meteo fetch + LLM_PROVIDERS + call_llm_api
├── charts.py               # Plotly 圖表工廠
├── styles.py               # 深色主題 CSS
├── openclaw_client.py      # 薄 subprocess wrapper（給訂閱頁用 OpenClaw CLI）
├── pages/
│   ├── 1_城市深入.py
│   ├── 2_城市並排比較.py
│   └── 3_個人訂閱.py
├── openclaw_agents/        # 5 隻龍蝦的 SOUL.md / IDENTITY.md（給 OpenClaw 進階用）
│   ├── collector/
│   ├── scraper/
│   ├── analyst/
│   ├── critic/
│   └── advisor/
├── openclaw_skills/
│   └── aqi-knowledge/      # SKILL.md +（跑 scripts/build_knowledge.bat 後填入 PDF）
├── scripts/
│   ├── build_knowledge.bat # 下載 WHO/EPA/Lancet 文獻
│   └── setup_cron.bat      # 註冊 OpenClaw 排程
├── docs/
│   └── knowledge_sources.md
├── requirements.txt
├── run.bat                 # Windows 雙擊啟動器
├── .streamlit/config.toml
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
