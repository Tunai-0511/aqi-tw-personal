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
