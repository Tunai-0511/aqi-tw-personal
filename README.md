# AgentAQI

AgentAQI 是以台灣空氣品質為核心的個人化健康資訊服務。目前專案由純 HTML／CSS／JavaScript 前端、FastAPI 後端與定時資料抓取流程組成；即使後端未啟動，前端仍可讀取排程產生的靜態 JSON。

> 本專案提供空氣品質資訊與一般性活動建議，不取代醫療診斷或專業醫療意見。

## 現有架構

```text
環境部／Open-Meteo／民間感測器
              │
              ├─ scripts/fetch_headless.py
              │      └─ docs/data/*.json（靜態資料）
              │
              └─ FastAPI（backend/）
                     ├─ 即時快照與歷史資料
                     ├─ 個人化建議與 RAG 聊天
                     └─ 多 Agent 執行流程與 SSE 事件

瀏覽器 ── docs/（靜態前端）── 靜態 JSON／FastAPI
```

主要能力：

- 顯示台灣各城市 AQI、污染物與 24 小時趨勢。
- 依常駐城市、空氣敏感程度、活動類型與個人門檻產生非敏感的個人化資訊。
- 顯示協調、採集、分析與建議 Agent 的真實執行事件。
- 提供城市搜尋／篩選／比較、主題切換與 RAG 聊天。
- 後端不可用時，以 `docs/data/` 的資料維持基本看板。

## 本機啟動

建議使用 Python 3.12（目前 GitHub Actions 排程也使用 3.12）。

### 1. 安裝後端相依

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. 啟動 FastAPI

```powershell
$env:EPA_KEY = "你的環境部 API 金鑰"          # 選填
$env:LLM_PROVIDER = "anthropic"              # 選填
$env:ANTHROPIC_API_KEY = "你的 LLM 金鑰"     # 選填
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Windows 也可以執行 `run_backend.bat`。後端啟動後可在 `http://127.0.0.1:8000/docs` 查看互動式 API 文件。

沒有 EPA 或 LLM 金鑰時，資料端點仍可啟動；實際資料來源與建議能力會依可用設定降級。

### 3. 啟動靜態前端

另開一個終端機：

```powershell
python -m http.server 8801 --directory docs
```

開啟 `http://127.0.0.1:8801`，再於頁面設定中填入 `http://127.0.0.1:8000`。若不指定後端，前端會使用 `docs/data/` 的靜態資料。

## 更新靜態資料

```powershell
python scripts/fetch_headless.py
```

輸出：

- `docs/data/latest_aqi.json`：最新城市快照與全國摘要。
- `docs/data/history.json`：各城市近 24 小時時序。
- `agent_export/latest_aqi.json`：供外部 Agent 整合使用的相容輸出。

`.github/workflows/update-aqi.yml` 目前會每小時執行同一支腳本，並將更新後的 JSON commit 回儲存庫。可在 GitHub Secrets 設定 `EPA_KEY`；LLM 相關 secrets 皆為選填。

## 環境變數

| 變數 | 用途 |
|---|---|
| `EPA_KEY` | 環境部 Open Data 金鑰 |
| `LLM_PROVIDER` | `anthropic`、`minimax`、`openai`、`gemini` 或 `custom` |
| `LLM_KEY` | 非 Anthropic 或通用 LLM 金鑰 |
| `ANTHROPIC_API_KEY` | Anthropic 金鑰 |
| `LLM_MODEL` | 一般分析、建議與聊天模型 |
| `LLM_BASE_URL` | 自訂 OpenAI 相容 API 端點 |
| `AQI_MODEL` | Anthropic Agent 協調模型 |
| `AQI_CORS` | 允許的前端來源，使用逗號分隔 |
| `AQI_SNAPSHOT_TTL` | 後端快照快取秒數，預設 600 |
| `AQI_FORCE_MOCK` | 設為 `1` 時，資料腳本產生本機測試資料 |

金鑰只應放在伺服器環境變數或 GitHub Secrets，請勿提交到儲存庫。

## API 摘要

| 方法與路徑 | 用途 |
|---|---|
| `GET /api/health` | 後端與模型設定狀態 |
| `GET /api/snapshot` | 最新城市快照 |
| `GET /api/history` | 24 小時城市時序 |
| `POST /api/pipeline/run` | 執行完整 Agent 流程 |
| `POST /api/coordinator/stream` | 以 SSE 傳送 Agent 執行事件 |
| `POST /api/advisor` | 產生單一城市個人化建議 |
| `POST /api/chat` | RAG 聊天 |

## 專案結構

```text
backend/                     FastAPI、Agent、RAG 與個人化邏輯
docs/                        純 HTML／CSS／JavaScript 前端
docs/data/                   排程產生的靜態資料
scripts/fetch_headless.py    無 UI 的資料抓取程式
data.py                      資料來源、清洗與共用資料契約
tsdb.py                      SQLite 時序快取與受信任本機工具資料
tests/                       自動化測試
.github/workflows/           GitHub Actions 排程
requirements.txt             後端相依
requirements-fetch.txt       排程抓資料所需的精簡相依
```

## 測試

```powershell
python -m unittest discover -s tests -v
```

## 公開部署前注意

未具使用者隔離的健康日誌 API 已停用；前端目前只在瀏覽器保存名稱、城市、敏感程度、活動與門檻等非敏感偏好。若要提供跨裝置帳號同步或健康紀錄，應先接上 Supabase Auth，以 `user_id` 建模並啟用 RLS，再加入同意／匯出／刪除流程。公開後端仍應替聊天、Pipeline 與 SSE 加上身分驗證、速率限制、使用額度與固定的 Cloudflare HTTPS API 入口。
