# 🤖 AgentAQI — 個人 agent 空氣品質監控平台

深色科技風 SaaS 監控介面。三個 agent（採集者 → 分析師 → 預警員）接力採集、分析、預警台灣 20 個縣市（含離島）的空氣品質。

---

## 💡 為什麼做這個專案

環境部已經公布每個縣市的 AQI,但「台中 AQI 95」對一個 72 歲 COPD 患者、或一個過敏性鼻炎的學生來說,
並沒有回答他真正想問的:「**我現在能不能出門?要不要戴口罩?**」官方數字是給「全民」的平均,不是給「你」的決策。

AgentAQI 的核心命題:**全民監控 → 個人健康決策**,四層價值:

1. **多源真實資料** — 五個公開 API(EPA 即時+歷史 / CAMS 模式 / 氣象 / 民生公共物聯網 / LASS)互補死角,無合成資料。
2. **收斂成「對你一個人」的答案** — 用你的年齡 / BMI / ICD-10 診斷 / 病歷 / 自設 AQI 閾值 + RAG 文獻
   (WHO 2021 / EPA NAAQS / Lancet 2023),算出今天還能在戶外幾小時、要哪種防護;
   **儀表板預設聚焦你的城市**(全台監控保留為決策脈絡 — 是錨定,不是過濾)。
3. **用你的日誌驗證敏感度** — 每天打卡症狀,系統對當日真實 AQI 算皮爾森相關 r,用你自己的數據證明空污對你的影響。
4. **把答案帶到你在的地方** — Pipeline 匯出一份 JSON,**已預裝的 Hermes bot** 在 Discord 讀它回答(拉取模型,不綁特定產品)。

AgentAQI 兩件事是分開的：

| 元件 | 角色 | 必填？ |
|------|------|--------|
| **直接 LLM API**（Anthropic / Gemini / MiniMax / OpenAI / 自訂） | Pipeline 中分析師 + 預警員的 LLM 呼叫 + 右下角 AI 助理 | ⭐ 必填一個 |
| **EPA Open Data Token**（環境部資料開放平臺） | 拉取 20 縣市即時 AQI | ⭐ 必填 |
| **Agent Bot**（讀 JSON 匯出 · Hermes 等任何 agent bot 皆可） | 在聊天平台(Discord / LINE…)回答空品(含個人化) | 已預裝（本機 Hermes 已綁 Discord;沒有 bot 也可全功能跑） |

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

### Step 3：（選填）填個人健康檔案 → 啟動 Pipeline

封面「**步驟 ① 個人健康檔案**」可先填年齡 / 已診斷疾病 / 我的 AQI 閾值 / 病歷,
再點「▶ 啟動三代理人 Pipeline」→ smooth scroll 到劇場區 → 3 個 agent 依序亮起跑分析（~10-30 秒）→ 主儀表板出來。
**先填再跑**,分析師 / 預警員第一次就會據你的檔案個人化(不必重跑)。

### Step 4（已就緒）：在 Discord 問 bot

本機已裝好 Hermes、裝了 `aqi-live` skill、以 `aqi-reporter` 人設綁定 Discord 頻道
**#每日空氣天氣報告**。跑完 Pipeline 會自動匯出 `hermes_export/latest_aqi.json`,
之後在頻道 `@bot 台中現在空氣如何` 即可(含 persona 個人化提醒)。詳見下方「🤖 Agent Bot 整合」段。

---

## 🎬 期末 demo 快速設置

要在課堂 demo「個人化推薦以後」(SECTION 08-10)時一打開就有豐富內容,不必現場等 API / 逐日打卡:

```powershell
# 1)(選配)灌 SECTION 08 的 demo AQI(過去 16 天 AQI 歷史 + 常駐城市污染事件軌跡)
雙擊 scripts\seed_demo_data.bat
#   或:  python scripts\seed_demo_data.py
#   清除:python scripts\seed_demo_data.py --clear
#   換城市:python scripts\seed_demo_data.py --city kaohsiung

# 2) 跑 run.bat 啟動 App
# 3) 封面「步驟 ① 個人健康檔案」展開表單,自行填入 persona(例:台北 72 歲 COPD)
# 4) 點「▶ 啟動三代理人 Pipeline」→ 分析師第一次跑就吃得到 persona(不必重跑)
```

健康日誌的「打卡紀錄」**不必灌** —— App 進 SECTION 09 會自動依「你城市當下生效的 AQI」
回填打卡紀錄(對齊真實 AQI,散點正相關是真的;跑了上面的 demo AQI 則點數更多)。
選配灌入的 demo AQI **全部標記為 demo、隔離在 `source='demo'`**,所以**demo 中途重跑
Pipeline 也不會被覆蓋**;`--clear` 後自動回讀真實資料。完整逐段講稿見
[`docs/demo_guide.md`](docs/demo_guide.md)。

> ⚠ demo 資料是為了展示而合成的(本專案正常運作時一律用真實外部 API)。請只在 demo 情境用,
> 並在簡報時誠實說明這幾天的歷史是 demo 資料。

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
| LLM 分析 | Anthropic / Google Gemini / MiniMax / OpenAI / 自訂 | 各自的 `/chat/completions` 或 `/v1/messages` | ✓ 你的 LLM key |
| 本機時序快取 | SQLite | `./agent_aqi.sqlite` | ✗ 純本機 |
| Hermes 拉取(取代推送) | 本機 JSON 匯出 | `hermes_export/latest_aqi.json` | ✗ 純本機 |

---

## 🤖 3 個 agent 接力 pipeline

| 內部 ID | UI 顯示 | 用 LLM？ | 工作 | 資料源 |
|---------|---------|--------|------|--------|
| `collector` | **採集者** | ❌ 純 ETL | EPA 即時抓取 + Open-Meteo 氣象 + 民生公共物聯網 / LASS 並行清洗 | 環境部 EPA `aqx_p_432` + Open-Meteo + 民生公共物聯網 SensorThings + LASS-net Airbox |
| `analyst`   | **分析師** | ✅ | 整合資料 + RAG 文獻檢索，產出 3 段風險分析（現況 / 健康建議 / 未來 6h 研判）| 採集者輸出 + RAG（WHO 2021 / EPA NAAQS / Lancet 2023 / 台灣 AQI 標準）|
| `advisor`   | **預警員** | ✅ | 接分析師的風險分級，**依使用者個人健康檔案（年齡 / BMI / ICD-10 診斷 / 病歷）為「所選城市」產出一份分節詳細建議**（現況風險 / 外出 / 防護 / 症狀警訊 / 一句總結；不再分五大族群，可一鍵換城市重生）| 上方資料 + 個人檔案 |

**為何只剩 3 個？**

初版設計過於追求「multi-agent」概念塞了 5 個 agent（採集者、爬蟲員、分析師、品管員 Critic、預警員），但其中 3 個的 LLM 呼叫只是「對剛跑完的 Python 程式碼寫一句註解」，沒有實際進入下游分析。Critic 的 0-100 分也沒實際 gate 任何重試。3-agent 重構把 ETL 集中在採集者（純資料處理、無 LLM），讓 LLM 只用在它擅長的「分析」與「個人化建議」兩個環節。`scraper/` 與 `critic/` 兩個 agent 工作區也於 2026-05-13 一併刪除。

`analyst` 與 `advisor` 用**同一個** LLM 提供商（你在 sidebar 選的那個）。Anthropic / Google Gemini / MiniMax / OpenAI / 自訂都可以。

---

## 📑 單頁結構（10 個 SECTION）

AgentAQI 是 Streamlit 單頁應用 — 從封面捲到底,依序為 10 個 SECTION:

| SECTION | 內容 |
|---------|------|
| 封面 | AgentAQI 品牌標題 + 「啟動三代理人 Pipeline」按鈕 + 狀態指示 |
| 01 三隻 agent 協作 | 像素風辦公室 + 3 個 agent 群組聊天室 |
| 02 即時 AQI 主儀表板 | 時間軸 scrubber + **預設聚焦你的城市**(點排行可切換)+ 排名 + 地圖 + 散點 + 資料時間燈號 |
| 03 24 小時趨勢 | AQI 趨勢線(預設只放你的城市,可多選比較)+ 7 天紀錄板(可切全台排行 / 📍 所選城市) |
| 04 污染物剖析 | 熱力圖 + 雷達圖 + 堆疊組成 + PM2.5 vs AQI 散點 |
| 05 環境關聯 | 濕度 vs PM2.5、風玫瑰 |
| 06 官方 vs 民間 | EPA 測站對比 CivilIoT / LASS-net 微型感測器 |
| 07 健康預警 | 頂部 = 預警員為**所選城市**寫的詳細個人化建議(可一鍵換城市重生);下方縣市卡**雙層門檻** — 你的城市依**你設定的閾值**、其他縣市依公定 AQI > 100(達標 📍 置頂,全部未達標顯示 all-clear)|
| 08 個人化推薦 | 常駐城市 + 個人健康檔案 → 個人化健康指數(以你的 AQI 閾值算,不分族群)+ 7 天趨勢 |
| 09 健康日誌 | 每日打卡(症狀分數 + 戶外時數)+ 症狀 vs AQI 相關性散點 |
| 10 Agent Bot | Pipeline 匯出 latest_aqi.json 供 Agent Bot(聊天平台)拉取 + 匯出狀態 |

主儀表板上方有**時間軸 scrubber** — 拖動可看過去 24h 任一時點的快照。主畫面點「🔍 查看 [city] 詳細」會開啟**城市深入 modal**(無頁面切換,捲動位置保留),內容由 `_city_detail.py` 共用。

右下角有**浮動 AI 助理 FAB**(LINE 風格聊天視窗),整合 RAG + LLM 回答空品相關問題。

**個人化錨點**:填了封面步驟①之後,各區的「預設視角」都以你的城市為中心 — SECTION 02 預設聚焦你的城市、
趨勢圖預設只放你的城市(可再多選)、雷達圖你的城市第一個、SECTION 03-05 所有圖表 📍 高亮所選城市
(趨勢粗線 / 熱力圖標籤 / 雷達加粗 / 散點放大描邊)、7 天紀錄板可切所選城市、
SECTION 07 預警員詳細建議跟著所選城市(可一鍵重生;縣市卡雙層門檻 — 你的城市用你設的閾值)。
全台 20 城市資料保留為決策脈絡(錨定,不過濾);換常駐城市時各區預設自動重新錨定,之後你在圖表裡的自選不會被強制改回。

**資料誠實**:畫面一律顯示「**絕對資料時間**」(不用會過期的「X 分鐘前」);頁面開著時自動更新**對齊 EPA 整點發布**
(跨入新的時鐘小時、過整點 10 分自動重抓;分頁關閉時不會更新 — Streamlit session 模型);EPA 失敗才退合成資料
且 UI 明確標示 MOCK;demo 資料隔離於 `source='demo'`、可一鍵清除。

---

## 🤖 Agent Bot 整合（已預裝 Hermes · 拉取 JSON · 不綁特定產品）

**本機已整合完成**:Hermes 已安裝、裝好本專案的 `aqi-live` skill、以 `aqi-reporter` 人設
綁定 Discord 頻道(**#每日空氣天氣報告**)、`AGENTAQI_EXPORT` 已指向本專案匯出檔。
跑完 Pipeline 後,直接在 Discord `@bot 台中現在空氣如何` 即可。
AgentAQI 主功能不依賴 bot(沒有 bot 也能全功能跑);契約只是一份 JSON,任何 bot 框架都能接。

### 怎麼運作（拉取模型,不是推送)

1. **Pipeline 跑完 → 匯出 JSON**:每次跑完 Pipeline,AgentAQI 會把這次結果(全台 20 城市快照 + 分析師摘要 + 預警員為所選城市的詳細建議 + 你在**封面步驟①**填的個人健康檔案)寫成 `hermes_export/latest_aqi.json`。
2. **Agent Bot 來這裡讀**:你自架的 agent bot 裝上本專案的 `hermes_skills/aqi-live/` skill(以 Hermes 為範例實作),讀那份 JSON。
3. **在聊天平台回答**:使用者打 `@bot 台中現在空氣如何`,bot 回最新數據 + 依 persona 的個人化提醒。換成別的 bot 框架,只要會讀這份 JSON 即可。

> **AgentAQI 的對接**沒有 webhook、沒有 cron 指令 — 資料是「你問、bot 才來讀」(pull),不是 AgentAQI 主動推。
> (repo 內另有組員的 Telegram **推播** watcher `external/cal-env-watch/`,那是獨立模組、不走這份匯出 — 見下方「姊妹模組」。)
> 匯出狀態(最後匯出時間 / 城市數 / 是否含個人檔案)可在主畫面 **SECTION · 10** 看到。

### 本機快速驗證（不用 Discord）

```powershell
# 先在 App 跑一次 Pipeline 產生 hermes_export\latest_aqi.json,然後:
python hermes_skills\aqi-live\read_export.py            # 全國概況
python hermes_skills\aqi-live\read_export.py 台北市      # 指定城市 + persona 提醒
```

印出的文字就是 Hermes 會貼進 Discord 的內容。匯出檔路徑可用環境變數 `AGENTAQI_EXPORT` 覆寫。

### Discord 晚報 `feel 1~5` 打卡 → 健康日誌

如果你的 Discord 晚報提示使用者直接回覆 `feel 1~5`，可以用內建 helper 把分數寫進 Streamlit 已有的 `health_diary` SQLite 表，SECTION · 09 會直接讀到同一份資料：

```bash
python scripts/record_feel.py "feel 4" --city taichung --outdoor-min 0 --note "Discord 晚報回覆"
```

支援格式：
- `feel 1` ~ `feel 5`
- `Feel: 4`
- 直接輸入 `4`

資料會寫入：
- `agent_aqi.sqlite`
- table: `health_diary`
- 欄位：`date`, `city_id`, `symptom_score`, `outdoor_min`, `note`, `created_at`

這個方案不需要 Discord button、interaction endpoint、ngrok 或 Cloudflare Tunnel；使用 Discord 原本輸入框即可。

### 姊妹模組:cal-env-watch（組員 · OpenClaw + Telegram 主動推播）

`external/cal-env-watch/` 是**組員交付的獨立模組**(原樣收錄,9 檔 SHA-256 驗證未修改):
以 **OpenClaw** 為 agent runtime,每 30 分鐘 cron 掃描 Google Calendar 未來 6 小時行程,
直接查該行程地點的 EPA `aqx_p_432` AQI 與 Open-Meteo 天氣,超過門檻就**主動推播 Telegram 預警**;
另附課表批次寫入 Google Calendar 的工具。與 AgentAQI 本體互補:

| | AgentAQI 本體 | cal-env-watch(組員) |
|---|---|---|
| 模型 | **拉取**(你問,bot 才讀 JSON 回答) | **推播**(行程要到了,主動警告) |
| Runtime / 平台 | Hermes / Discord | OpenClaw / Telegram |
| 資料路徑 | Pipeline 匯出 `latest_aqi.json` | 直接打 EPA API(行程地點對位) |
| 場景 | 「現在空氣如何?」問答 | 「2 小時後上課地點 AQI 157」事前提醒 |

同一個 EPA 資料源、兩種 runtime、兩種傳遞模型 —— 正是「**不綁特定產品**」的實證。
注意:該模組的金鑰與工作目錄寫死在組員機器(`C:\Users\User\.openclaw\`),
**本機不直接執行**(demo 範圍外);門檻為其自訂常數(50/100/150),不影響本體的個人化閾值。

### 在另一台機器重建整合（參考;本機不需要）

1. 安裝並啟動 Hermes(`hermes` CLI)。
2. 把 `hermes_skills/aqi-live/` 裝給 Hermes、`hermes_agents/aqi-reporter/` 作為 bot 人設。
3. Discord Developer Portal 開 Bot → 邀請進伺服器 → 綁到 Hermes;
   設環境變數 `AGENTAQI_EXPORT` 指向 `hermes_export/latest_aqi.json`。
4. 在 Discord `@bot` 問空品即可。詳見 [`hermes_skills/aqi-live/SKILL.md`](hermes_skills/aqi-live/SKILL.md)。

> JSON 契約欄位見 `hermes_skills/aqi-live/SKILL.md`;產生邏輯在 [`data.py`](data.py) 的
> `build_hermes_payload()`,寫檔在 [`app.py`](app.py) 的 `_write_hermes_export()`。

---

## 🏗 架構

```
┌──────────────────────────────────────────────────────────────┐
│                        使用者瀏覽器                            │
└────────────────────────┬─────────────────────────────────────┘
                         │ localhost:8501
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  AgentAQI Streamlit                                         │
│  - 封面 / 劇場 / 10 個 SECTION(02-10 主要儀表板區)             │
│  - 群組聊天室 + 右下角 AI 助理 + 城市深入 modal                 │
│  - 封面步驟① 個人健康檔案 + 時間軸 scrubber + 健康日誌          │
└──┬───────────────────────────────────────────────────────────┘
   │
   ├──── HTTP ────► data.moenv.gov.tw           (環境部 EPA 即時 aqx_p_432 + 歷史 aqx_p_488)
   ├──── HTTP ────► sta.colife.org.tw           (民生公共物聯網 SensorThings · 智慧城鄉空品微型感測器)
   ├──── HTTP ────► pm25.lass-net.org           (LASS-net Airbox 社群網路 · 補充離島)
   ├──── HTTP ────► api.open-meteo.com          (氣象，免金鑰)
   ├──── HTTP ────► air-quality-api.open-meteo  (CAMS 大氣化學模式，免金鑰)
   ├──── HTTP ────► Anthropic / Google Gemini / MiniMax / OpenAI / 自訂
   │                 (sidebar 選的 LLM 提供商；in-app 即時回應)
   │
   ├──── SQLite ──► ./agent_aqi.sqlite        (本機時序快取 + 健康日誌；跨重啟保留)
   └──── write ──► ./hermes_export/latest_aqi.json
                          (Pipeline 跑完匯出;Agent Bot「來這裡讀」回答 —
                           拉取模型,不是 AgentAQI 主動推。詳見「Agent Bot 整合」段)

           ┌──────────────────────────────────────────────┐
   讀取 ◄──┤ Agent Bot(聊天平台 · hermes_skills/aqi-live)  │──► 在聊天平台回答(含 persona)
           └──────────────────────────────────────────────┘
```

**為什麼是「拉取」不是「推送」？** 不必架 webhook、不必註冊 cron;使用者在 Discord 問了,Hermes 才來讀最新匯出回答。資料只在本機 JSON,Hermes 與 AgentAQI 解耦 —— 換成別的 bot 框架也只要會讀這份 JSON 即可。

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
| SECTION 10 顯示「尚未匯出」 | 還沒跑過 Pipeline;跑一次就會產生 `hermes_export/latest_aqi.json` |
| `read_export.py` 找不到匯出檔 | 先在 App 跑一次 Pipeline,或設環境變數 `AGENTAQI_EXPORT` 指到檔案 |
| Discord `@bot` 沒回 | 確認 Hermes gateway 在跑(`hermes gateway status`)、已跑過一次 Pipeline、`AGENTAQI_EXPORT` 指向正確路徑 |
| Port 8501 被佔 | 改 `.streamlit/config.toml` 的 `server.port` |

---

## 📁 檔案結構

```
aqi-tw-personal-2/
├── app.py                  # Streamlit 主入口（封面 + 10 個 SECTION + 城市深入 modal + AI 助理）
├── data.py                 # EPA / Open-Meteo / CivilIoT / LASS fetcher + LLM_PROVIDERS + call_llm_api
├── tsdb.py                 # SQLite 本機時序快取(aqi_snapshots / cams_hourly / health_diary)
├── charts.py               # Plotly 圖表工廠
├── styles.py               # 深色主題 CSS
├── _city_detail.py         # 城市深入 modal 共用渲染(底線前綴避免被 Streamlit pages 探索)
├── hermes_export/          # Pipeline 匯出的 latest_aqi.json(已預裝的 Hermes bot 來讀)
├── hermes_agents/          # Agent Bot 人設(已註冊到本機 Hermes)
│   └── aqi-reporter/       # IDENTITY / SOUL / TOOLS / USER.md
├── hermes_skills/          # Hermes skill(已安裝到本機 Hermes)
│   └── aqi-live/           # SKILL.md + read_export.py(讀 latest_aqi.json 格式化回覆)
├── external/
│   └── cal-env-watch/      # 組員模組(OpenClaw):行事曆×環境「事前預警」推播 Telegram
│       ├── SKILL.md        #   原樣收錄(SHA-256 驗證未修改);設定綁組員機器,本機不執行
│       ├── scripts/        #   cal_env_watch.py(watcher)+ 課表寫入 + Calendar MCP server
│       └── references/     #   門檻表 / 地點表 / 金鑰配置 / 踩雷紀錄
├── scripts/
│   ├── seed_demo_data.py   # 期末 demo 假資料灌庫(AQI 歷史;健康日誌由 App 自動回填)
│   ├── seed_demo_data.bat  # ↑ 的 Windows 雙擊版(自動 activate venv)
│   ├── record_feel.py      # Discord 晚報 `feel 1~5` → 寫進 health_diary
│   └── _fix_hermes_bind.py # Hermes config.yaml 安全重綁 helper(YAML emitter)
├── docs/
│   ├── demo_guide.md       # 期末 demo 逐段講稿(SECTION 08-10)
│   └── 答辯準備.md          # 口試 Q&A(動機 / 程式講解 / 導師可能問的問題)
├── tests/                  # 單元測試(record_feel → health_diary)
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

## 🤖 為什麼叫 AgentAQI

早期版本叫 **LobsterAQI** —— 🦞 龍蝦視覺主題是致敬 [OpenClaw](https://github.com/openclaw/openclaw) 的 lobster 主題。但實際對外整合用的是 **Agent Bot 拉取 JSON**(以 Hermes 為範例),並非 OpenClaw,龍蝦品牌已名實不符。因此改名 **AgentAQI** + 🤖 機器人主題,直接點出「個人 agent 空氣品質監控」的定位 —— **本體**不綁特定產品、對接不走推送 / cron。(repo 內 `external/cal-env-watch/` 是組員以 OpenClaw 實作的獨立預警模組 —— 同一資料源、不同 runtime 的對照示範,反而印證「不綁產品」:本體接 Hermes、組員接 OpenClaw,誰會讀資料誰就能接。)
