# 🦞 LobsterAQI 變更紀錄

本檔案記錄每次對專案的修改。新版本放在最上方,沿用 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/) 格式。

分類標籤:
- `Added` 新功能
- `Changed` 既有功能變更
- `Fixed` Bug 修復
- `Removed` 移除功能
- `Deprecated` 即將移除
- `Security` 安全性

---

## [2026-05-14] 大規模加上繁體中文詳細註解

### Documented
為整個專案的 Python 程式碼加上完整的繁體中文註解 — 讓未來接手者(或自己)
快速理解每個模組 / 函式 / 區塊的用途。

**模組層級**:每個檔案頂部新增完整的 docstring,說明該檔的職責與整體結構。

**函式層級**:所有 public 函式都有詳細 docstring,包含:
- 功能說明(做什麼、為什麼)
- Parameters 含意
- Returns 含意
- 重要的非顯式行為(例:失敗時回 None、idempotent 等)

**區段層級**:每個 `# ===` SECTION 分隔線下方加上中文說明,標出該區塊內容。

**內聯註解**:複雜邏輯加上 `# 註解` 解釋「為什麼這樣寫」(而非「做什麼」)。

### Per-file Summary
- **[_city_detail.py](_city_detail.py)** (196 行) — 完整重寫成中文註解版,涵蓋 hero 區、Row 1 圖表、Row 3 預警員建議的渲染邏輯
- **[tsdb.py](tsdb.py)** (354 行) — 完整重寫,深入解釋為什麼用 SQLite、兩種 source 的設計、schema 遷移流程
- **[charts.py](charts.py)** (501 行) — 完整重寫,每個 Plotly 圖表工廠函式都有詳細說明:用途、視覺設計、特殊參數
- **[data.py](data.py)** (1312 行) — 模組 docstring + 主要函式 docstring + 區段標頭中文化。重點:
  - 靜態參考資料(CITIES / AQI_LEVELS / POLLUTANTS)的設計理由
  - 合成生成器(mock fallback)的數學模型(日夜雙峰、城市偏差、加權風險)
  - 真實 API fetcher 區段(EPA / CAMS / CivilIoT / LASS)的端點選擇與容錯邏輯
  - LLM 多 provider 切換的設計理由(直接 HTTP vs OpenClaw gateway)
- **[app.py](app.py)** (2670 行) — 模組 docstring + session_state 逐欄解釋 + 所有 SECTION 中文標頭。重點:
  - 整體頁面架構(封面 → 4 個 SECTION → 個人訂閱)
  - `init_state()` 每個欄位的用途與預設值理由
  - `_auto_refresh_tick` fragment 的工作機制
  - **RAG 整段詳細說明**:RAG_SNIPPETS 內容、`_score_chunk` n-gram 演算法、retrieve top-k 策略
  - `run_pipeline()` 三 agent 執行流程
  - `_render_chat_panel()` AI 助理對話流程(RAG + LLM 整合)

### Skipped
- **[styles.py](styles.py)** (1302 行) — 主要是 CSS 字串而非 Python 邏輯,
  CSS 內已有英文 `/* ... */` 註解標示各區塊用途,不再額外加中文

### Verification
```powershell
cd C:\Users\tunai\Downloads\aqi-tw-personal-main
.venv\Scripts\python.exe -m py_compile app.py charts.py styles.py _city_detail.py data.py tsdb.py
```
- 全部通過 syntax 檢查
- 沒有改變任何執行邏輯,純註解 / docstring / 區段標頭
- _city_detail.py、tsdb.py、charts.py 是「完整重寫」並順便清掉小型 dead code
  (例:_city_detail.py 移除 unused import `best_outdoor_hours`、`make_outdoor_bars`)

---

## [2026-05-14] 死碼清理:刪除無人呼叫的函式、未使用 CSS、空檔案與廢棄 agent 目錄

### Removed
- **`data.py` 內 3 個無人呼叫的函式**:
  - `generate_forecast()`(原 L201-218,~19 行)— 之前刪除預測 UI 後失去呼叫者
  - `generate_history_with_forecast()`(原 L221-241,~23 行)— 同上
  - `generate_cleaning_report()`(原 L289-304,~17 行)— 用 `random.randint` 偽造清洗統計,已被 `fetch_citizen_sensors()` 真實版取代
- **`charts.py` 內 `make_forecast_chart()`**(原 L281-323,~43 行)— 與上面三個函式同期失去呼叫者
- **`styles.py` 內 `.agent-report*` CSS 全系列**(原 L862-955,~94 行 / 15 個選擇器)— 第三輪 Fix-5 把 agent 卡片改用 `st.columns + st.expander + st.markdown` 後,此 CSS 已無 HTML 引用
- **根目錄空檔 `OpenClaw Setup`**(0 bytes)— 殘留,無內容
- **`openclaw_agents/critic/`、`openclaw_agents/scraper/` 整個目錄**(共 ~51 KB / 12 個 .md 檔)— 早期 5-agent 設計遺物,3-agent refactor 已不再啟用,`data.py:368-378` 也明確註解「Critic 移除、Scraper 併入 collector」
- **`__pycache__/` 目錄**(~312 KB,6 個 .pyc) — 跑一次自動重生,無保留必要

### Total
程式碼 ~196 行 + CSS ~94 行 + 12 個 .md + 7 個自動生成檔 + 1 空檔。`openclaw_agents/` 從 5 個子目錄縮為 3 個(advisor / analyst / collector),與 README 描述一致。

### Verification
```powershell
cd C:\Users\tunai\Downloads\aqi-tw-personal-main
.venv\Scripts\python.exe -m py_compile app.py charts.py styles.py _city_detail.py data.py tsdb.py
```
- `python -m py_compile` 全綠通過
- `Grep` 確認:`generate_forecast|generate_history_with_forecast|generate_cleaning_report|make_forecast_chart|agent-report` 在程式碼層面已完全消失(只剩 CHANGELOG.md 歷史紀錄)
- `find . -type f -size 0`(排除 .venv / .git)無結果 — 沒有殘留空檔
- `ls openclaw_agents/` 只剩 advisor / analyst / collector

---

## [2026-05-13] 第三輪修復:agent 卡片排版 + 刪除多頁 + 個人訂閱併入主 app + 刪預測 + 自動更新

### Fixed
- **預警員/分析師卡片排版錯亂**([app.py:1671-1720](app.py)) — 原本用 `escape(text) + <details>` 把 LLM markdown 整段轉成 escaped HTML 配 `pre-wrap`,結果 `#`、`##` 等 markdown 標記變成可見字元,長度差異又造成詭異的大段空白。改為:
  - 改用 `st.columns(2) + st.expander + st.markdown`,讓 LLM 的 markdown(標題、表格、清單)正確渲染
  - 新增 `_strip_redundant_heading()` 把 LLM 自動加上的「# 🚨 空氣品質健康預警通知」等 H1/H2 標題剝掉,避免與外層 eyebrow 重複

### Added
- **每小時自動更新數據**([app.py:131-156](app.py)、[app.py:73-79](app.py)) — 原本 Pipeline 啟動後資料就靜止,使用者必須手動按「↻ 重新執行」。現在:
  - 新增 sidebar toggle「🔄 每小時自動更新數據」(預設開啟)
  - 用 `st.fragment(run_every="60s")` 每分鐘檢查上次跑 Pipeline 的時間
  - 若距上次 ≥ 60 分鐘 → 自動觸發 `run_pipeline()` 並 `st.rerun(scope="app")` 重整全頁
  - 新增 session_state `auto_refresh_enabled`(bool)與 `last_pipeline_run_at`(datetime)
  - sidebar 顯示「上次跑 X 分鐘前 · 下次自動約 Y 分鐘後」
- **個人訂閱併入主 app**([app.py:2515-2622](app.py)) — 原 `pages/3_個人訂閱.py` 整段表單(城市/敏感族群/AQI 閾值/推送頻道/cron 頻率)併到主 app footer 之前,成為 SECTION · 04。所有 widget key 加 `sub_` 前綴避免衝突。

### Removed
- **整個多頁結構**(刪除 `pages/1_城市深入.py`、`pages/2_城市並排比較.py`、`pages/3_個人訂閱.py`,目錄變空) — 使用者反映 sidebar 多頁面太雜亂。城市深入仍可透過主畫面「🔍 查看 X 詳細」按鈕開啟 modal(走 `_city_detail.py`,功能保留),其餘兩頁完全廢除。
- **6 小時 AQI 預測**([app.py:1923-1973 → 1923-1955](app.py)) — 預測功能對使用者價值有限(且 `best_outdoor_hours` 是合成資料),已有訂閱推送可獲取未來資訊。修改:
  - 主 app SECTION · 03 從「趨勢與預測」改為「24 小時趨勢」,刪除 t2 預測欄,t1 改為全寬
  - 移除 `make_forecast_chart`、`generate_history_with_forecast` 兩個 import
  - `_city_detail.py` 同步刪除 Row 2 的「未來 6 小時 AQI 預測」與「最佳外出時段」整列(後者也用 `best_outdoor_hours` 合成資料)

### Verification
```powershell
cd C:\Users\tunai\Downloads\aqi-tw-personal-main
.venv\Scripts\python.exe -m py_compile app.py charts.py styles.py _city_detail.py data.py
.venv\Scripts\Activate.ps1
streamlit run app.py
```
功能測試清單:
- [ ] 主畫面 sidebar 左側只有 LobsterAQI 一個 app,沒有 城市深入 / 城市並排比較 / 個人訂閱 三個分頁
- [ ] 跑 Pipeline 完成後,預警員 + 分析師卡片以「並排可摺疊」呈現,展開後 markdown 標題/表格正確顯示,沒有可見的 `#` 字元
- [ ] SECTION · 03 標題為「24 小時趨勢」,只有一張全寬 AQI 趨勢圖,沒有「6 小時 AQI 預測」
- [ ] 城市深入 modal 仍可開啟(點主畫面「🔍 查看 X 詳細」),但裡面沒有 6h forecast / 最佳外出時段 兩張圖
- [ ] 主畫面最底部 footer 上方有 SECTION · 04「個人訂閱 · 把預警送到你的 Discord / LINE」表單
- [ ] sidebar 有「🔄 每小時自動更新數據」toggle,預設開啟;啟動 Pipeline 後 sidebar 顯示「上次跑 X 分鐘前」

---

## [2026-05-13] 第二輪修復:時間戳 + AQI 一致性 + 聊天框 + 刪除區域聚合

### Fixed
- **時間戳顯示誤導使用者**([app.py:1763-1789](app.py)) — 原本只顯示「⚡ 顯示即時資料(05/12 23:00)」,使用者誤以為資料是即時的但其實落後 15+ 小時。改為三段資訊:
  - 🟢/🟡/🔴 新鮮度燈號(< 90 分鐘 / < 4 小時 / 更久)
  - 現在實際時間 + 24h 歷史最新時間 + 落後分鐘數
  - EPA 即時測站平均落後分鐘數(來自 `snapshot.updated_min_ago`)
- **AQI 數值在「地理分佈」與「熱力圖」不一致**([app.py:1855-1864](app.py)、[app.py:1957-1974](app.py)) — 根因是三圖用了三個不同 API(`aqx_p_432` 即時 / `aqx_p_488` 歷史 / Open-Meteo CAMS 模型),數值不同是預期行為但 UI 沒解釋。修復:
  - 地理分佈副標明示「資料來源:EPA aqx_p_432(環境部測站即時值)」
  - 熱力圖區段新增摺疊「📖 三個 AQI 來源差異對照表」說明三個 API 的性質、更新頻率、涵蓋範圍
- **AI 助理對話框「問一次就不能繼續輸入」**([app.py:1393-1402](app.py)) — LLM 25 秒阻塞期間 widget 狀態未正常釋放。修復:LLM 回應寫入 history 後加 `st.rerun()` 強制刷新 chat_input widget。
- **AI 助理輸入框未常駐對話框底部**([styles.py:1111-1146](styles.py)) — 當對話歷史短(例如只有歡迎訊息)時,輸入框會浮在中間。修復用三道 CSS 保險:
  - `.st-key-floating_chat [data-testid="stChatInput"]`:加 `margin-top: auto`、`flex-shrink: 0`、`order: 99`
  - `.st-key-chat_history`:加 `display: flex`、`flex-direction: column`、`justify-content: flex-end`、`order: 1`,讓歡迎訊息與短對話貼底
  - 順便修正原檔案 line 1133 的 CSS 註解開頭 `\*` 為正確的 `/*`

### Removed
- **「區域聚合」環形圖**(刪除 [app.py:50](app.py) import、[app.py:1853-1857](app.py) UI 區塊、[charts.py:331-357](charts.py) `make_region_donut` 函式) — 使用者反映此功能不需要。連帶將主儀表板第一列從三欄(3:4:3)改為兩欄(3:5),讓城市排名圖更寬。

### Verification
```powershell
cd C:\Users\tunai\Downloads\aqi-tw-personal-main
.venv\Scripts\python.exe -m py_compile app.py charts.py styles.py   # 語法檢查
.venv\Scripts\Activate.ps1
streamlit run app.py
```
功能測試清單:
- [ ] 頂部時間戳顯示三段資訊(現在 / 歷史最新 / EPA 落後)
- [ ] 熱力圖上方有可摺疊的「📖 三個 AQI 來源差異對照表」
- [ ] 主儀表板第一列只有兩欄(聚焦城市 + 排名),沒有環形圖
- [ ] 開啟聊天面板 → 連發 5 則訊息,每則之間 input 應自動清空可繼續輸入
- [ ] 聊天面板輸入框永遠在最底部,即使對話只有歡迎訊息也是

---

## [2026-05-13] 第一輪審查報告(無程式碼變更)

### Documented
- 完成首次「人因工程視覺感受 + 虛假資料」全面審查,共發現 17 項問題:
  - **虛假資料**:🔴 3 項(updated_min_ago 隨機、清洗報告隨機、整個 generate_current_snapshot 用 np.random)、🟡 3 項(fallback 自動降級無警告)、🟢 1 項
  - **視覺人因**:🔴 2 項(--text-muted 違反 WCAG AA、Hero 區資訊過載)、🟡 5 項(AQI 色碼偏離台灣 EPA、發光特效過強、缺 tabular-nums、Legend 遮擋、Plotly margin 不統一)、🟢 3 項
- 計畫文件位於 `C:\Users\tunai\.claude\plans\soft-tumbling-nest.md`(後被第二輪覆寫)。

---

## 紀錄規範

未來新增條目時請遵守:

1. **日期格式**:`[YYYY-MM-DD]` 後接簡短主題,例如 `[2026-05-13] 修復時間戳 bug`
2. **每條變更**用 `Added / Changed / Fixed / Removed / Deprecated / Security` 分類
3. **附上檔名:行號**用 markdown link 格式 `[app.py:1234](app.py)` 方便點擊跳轉
4. **重要 bug 修復**寫明「原本怎樣 → 改成怎樣」與根因
5. **驗證步驟**有必要時附上具體指令與 checklist
