# LobsterAQI · 知識庫來源與授權

LobsterAQI 的 `analyst` / `advisor` 在 RAG 模式下會引用以下文獻。把它們下載到
`openclaw_skills/aqi-knowledge/docs/`（或執行 `scripts/build_knowledge.bat`
自動下載）後，agent 就會直接引用真實段落，而不是寫死的 RAG snippets。

---

## 一級（必裝）

### 1. WHO Air Quality Guidelines 2021

**全名**：WHO global air quality guidelines: particulate matter (PM2.5 and PM10), ozone, nitrogen dioxide, sulfur dioxide and carbon monoxide

- **PDF（直接下載）**：https://iris.who.int/server/api/core/bitstreams/551b515e-2a32-4e1a-a58c-cdaecd395b19/content
- **目錄頁**：https://iris.who.int/handle/10665/345329
- **授權**：CC BY-NC-SA 3.0 IGO（**可以重發**，需附引用、非商業使用、衍生作品須同樣授權）
- **檔案大小**：約 3.6 MB
- **重要章節**：
  - Chapter 2: PM2.5 限值 — 年均 5 μg/m³、24h 15 μg/m³
  - Chapter 3: O3 限值 — 8h 100 μg/m³
  - Chapter 4: NO2 限值 — 年均 10 μg/m³
  - Annex: 敏感族群指引

### 2. US EPA NAAQS（National Ambient Air Quality Standards）

- **HTML 表格**：https://www.epa.gov/criteria-air-pollutants/naaqs-table
- **PDF 版本**：https://www.epa.gov/sites/default/files/2016-04/documents/criteria.pdf（較舊）
- **授權**：US Federal Government works → **Public Domain**，完全自由使用
- **重點數值**：
  - PM2.5 24h 平均：35 μg/m³（Primary）
  - PM2.5 年均：12 μg/m³（Primary）
  - O3 8h：0.070 ppm
  - AQI > 100 → 對敏感族群不健康

### 3. 環境部 · 台灣空氣品質指標

- **HTML 頁面**：https://airtw.moenv.gov.tw/CHT/Information/Standard/AirQualityIndicator.aspx
- **即時資料 API**：https://data.gov.tw/dataset/40448
- **授權**：[Taiwan Open Government Data License v1.0](https://data.gov.tw/license)
- **重點**：
  - AQI 六級分類（良好 / 普通 / 對敏感族群不健康 / ...）
  - 各等級對應的健康影響與行動建議
  - 計算公式（取各污染物子指標的最大值）

### 4. Lancet Planetary Health 2023 · PM2.5 + 心血管

- **文章頁**：https://www.thelancet.com/journals/lanplh/article/PIIS2542-5196(23)00047-5/fulltext
- **DOI**：10.1016/S2542-5196(23)00047-5
- **授權**：依文章而定（Lancet Planetary Health 多數開放存取，CC BY 4.0）
- **重點發現**：
  - 高 PM2.5 暴露時劇烈運動，肺部沉積量提升 3-5 倍
  - 對心血管疾病患者的具體建議：AQI > 100 時避免戶外有氧運動

---

## 二級（建議裝）

### 5. WHO 2021 Annex（空氣污染對健康的入門）

- https://www.who.int/health-topics/air-pollution
- 適合給非專業使用者看的概論

### 6. State of Global Air（Health Effects Institute）

- https://www.stateofglobalair.org/
- 每年更新的全球空品狀態報告，含台灣排名
- 互動式視覺化（不適合 ingest 成 PDF，但可放連結）

### 7. 環境部 · 空氣品質常見問答

- https://airtw.moenv.gov.tw/CHT/Information/QA/Page1.aspx
- 民眾常問問題（口罩、淨水器、室內 vs 室外）

---

## 不建議放進 RAG 的（但可以引用連結）

- 各廠商空氣清淨機型錄（商業偏差）
- 維基百科條目（次級來源，內容不穩定）
- 新聞報導（時效性問題）

---

## 引用格式建議

當 `analyst` / `advisor` 引用上方文獻時，輸出末尾應附：

```
📚 引用：
- WHO Air Quality Guidelines 2021, Chapter 2 (PM2.5)
- 環境部 AQI 標準（airtw.moenv.gov.tw）
```

不要編造 chapter / page number — 只在確定的時候才寫。

---

## 代理人外部工具 — Twinkle Hub MCP（選配，非核心資料源）

> 這一節跟上面的 RAG 文獻**性質不同**：它不是要 ingest 的 PDF / HTML，而是一個讓
> OpenClaw 代理人「即時查詢」的 MCP 工具。儀表板的所有數字仍來自 `data.py`
> （環境部 + Open-Meteo CAMS + 民生公共物聯網 + LASS / AirBox），**完全不受此工具影響**。

**Twinkle Hub**（https://hub.twinkleai.tw/）是「MCP-as-a-Service」：一把可撤銷的
`sk-...` 金鑰，讓 MCP 客戶端用自然語言查詢台灣政府開放資料（data.gov.tw，約 4.9 萬個
資料集）。我們把它接給 `analyst` / `advisor`，**只當作補充背景脈絡的工具**——查當下
天氣 / 鋒面 / 降雨 / 颱風 / 沙塵 / 環境與健康公告，用來「解釋」空品為什麼變化。

### 註冊方式（一次性）

雙擊執行 `scripts/setup_twinkle_hub.bat`，貼上在 https://hub.twinkleai.tw/login
（Google / GitHub 登入）取得的 `sk-...` 金鑰即可。腳本實際做的事：

```
openclaw config set mcp.servers.twinkle-hub.url "https://api.twinkleai.tw/mcp/"
openclaw config set mcp.servers.twinkle-hub.transport "streamable-http"
openclaw config set mcp.servers.twinkle-hub.headers.Authorization "Bearer sk-..."
```

寫完設定後需**重啟 gateway**（`openclaw gateway stop` 再 `start`，或前景模式 Ctrl+C
後重跑 `openclaw gateway run`）才會生效。MCP 伺服器是**全域**設定，`--session isolated`
的 cron 排程會自動繼承，因此 `app.py` 與 `scripts/setup_cron.bat` 的 `openclaw cron add`
指令**不需要改**。

### 工具範圍

Hub 提供 5 個 `opendata-*` 工具 + 32 個 `twtools-*` 公用工具（身分證 / 統編 / 民國年
換算等）。代理人**只用 `opendata-*`**；`twtools-*` 與空品無關，已在 SOUL.md 指示忽略。
（此版 OpenClaw 2026.5.7 沒有 per-server 工具過濾參數，因此靠代理人守則約束，而非設定。）

### 重要警語（已寫進 analyst / advisor 的 SOUL.md + IDENTITY.md）

- **不是獨立量測**：Hub 的 AQI 本質仍是環境部來源，數字會跟 `data.py` 直接抓的一樣。
  代理人只拿它補質性背景，**絕不**用 Hub 的數字覆蓋訊息裡既有的 AQI / PM2.5。
- **Alpha、會降級**：每天 22:00–07:00（台灣時間）維護、可能不穩、無 SLA、未來改為
  逐工具預付計費。代理人被要求**優雅降級**——工具逾時 / 報錯就直接用 prompt 裡的儀表板
  數據完成摘要，不卡住、不重試到死。
- **隱私紅線**：訂閱推播會把使用者個人健康檔案（年齡 / BMI / 診斷 / 病歷）內嵌進 prompt。
  代理人被明確禁止把這些送進 Hub 查詢，**只用公開的地點 / 天氣 / 環境關鍵字**。

### 品管員（critic）的配套判定

`critic`（agent-k，反幻覺審稿，**僅存在於部署中的代理人工作區、repo 未收錄**）的 SOUL.md
也加了一條判定規則：分析師若引用 `opendata-*` 來的**質性**天氣 / 環境背景（鋒面 / 颱風 /
沙塵等）**不算幻覺、不扣分**；但 AQI / PM2.5 **數字**仍以快照為準，Hub 數字覆蓋快照照樣
重扣。沒這條，critic 會把合法的天氣脈絡誤判成幻覺而退稿。

### 授權與移除

- Twinkle Hub 服務：見 https://hub.twinkleai.tw/ 的條款（alpha 階段、未來轉付費）。
- 底層資料：data.gov.tw，多數採 [台灣政府資料開放授權條款](https://data.gov.tw/license)。
- 移除工具：`openclaw mcp unset twinkle-hub`（再重啟 gateway）。
