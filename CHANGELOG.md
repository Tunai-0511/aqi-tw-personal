# 🤖 AgentAQI 變更紀錄

本檔案記錄每次對專案的修改。新版本放在最上方,沿用 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/) 格式。

分類標籤:
- `Added` 新功能
- `Changed` 既有功能變更
- `Fixed` Bug 修復
- `Removed` 移除功能
- `Deprecated` 即將移除
- `Security` 安全性

---

## [2026-06-11] 命名中性化:hermes_* → agent_*(契約不綁框架)

### Changed
- **改名**(契約是給任何 agent bot 的 — 包括 OpenClaw — 名字不該綁 Hermes):
  `hermes_export/` → `agent_export/`、`hermes_skills/` → `agent_skills/`、
  `hermes_agents/` → `agent_personas/`、`build_hermes_payload()` → `build_agent_payload()`、
  `_write_hermes_export()` → `_write_agent_export()`。散文中「本機範例:Hermes」保留。
  全 repo ~60 處引用同步(app / data / README / demo_guide / SKILL / 人設檔)。
- **Hermes runtime 同步**:profile `.env` 的 `AGENTAQI_EXPORT` 改指 `agent_export/`;
  安裝副本重新同步;gateway 重啟驗證(discord connected、port 8645、config 解析 ✓)。

### Fixed
- **config.yaml 二度損壞(01:04,Hermes 自身 config writer 的長字串 bug)→ 根治**:
  `discord.channel_prompts` 不再內嵌 1900+ 字完整 persona,改為 ~300 字精簡指令
  (指向已安裝 aqi-live skill 與 `AGENTAQI_EXPORT`);完整人設留在 skill / repo 文件。
  `scripts/_fix_hermes_bind.py` 同步改寫成短 prompt 版,之後重跑不會再引入脆弱長字串。

---

## [2026-06-10] 收錄組員模組 cal-env-watch(原樣 vendored)

### Added
- **`external/cal-env-watch/`** — 組員交付的獨立模組(OpenClaw runtime):Google Calendar ×
  天氣 × AQI 的「行程事前主動預警」,每 30 分鐘 cron 掃描未來行程,該地點 AQI / 雷雨超標就推
  Telegram;另含課表批次寫入 Google Calendar 的工具。**9 個檔案逐一 SHA-256 驗證,與組員原檔
  byte-level 一致(未做任何修改)**。來源:`Downloads/SKILL.md` + `scripts-20260609T162715Z-3-001`
  + `references-20260609T162714Z-3-001`。
- 與本體的關係寫進 README「Agent Bot 整合 · 姊妹模組」:本體 = Hermes/Discord **拉取問答**,
  cal-env-watch = OpenClaw/Telegram **行程推播** — 同一 EPA 資料源、兩種 agent runtime,
  互補場景、也是「不綁特定產品」的實證。注意:其設定寫死在組員機器
  (`C:\Users\User\.openclaw\`),本機不直接執行(demo 範圍外)。
- `.gitignore` 加防呆:擋 `external/**/secrets/`、`google-cal*.json`、`moenv.json`
  (組員模組引用的 OAuth/金鑰檔永不入 repo;經稽核,vendored 檔案本身零夾帶金鑰)。

---

## [2026-06-09] 架構圖連線拉直 + 直書標題改水平 + 步驟①置中 + 擋 Clear cache 快捷鍵

### Fixed
- **封面「步驟 ①」標題沒置中**:`.eyebrow` 是 `display:inline-block`,在其上加 `text-align:center` 只置中
  藥丸內文字、藥丸本身仍靠左。改成外層包一個 `text-align:center` 的 block 再放 inline-block 藥丸。([app.py](app.py))
- **「Clear caches」對話框一直跳**:那是 Streamlit 內建單鍵快捷鍵 **C(Clear cache)/ R(Rerun)** —— 焦點不在
  輸入框時隨手按到就觸發(本專案根本沒有 `@st.cache_data`,清了也沒作用,只是惱人)。新增
  `_install_hotkey_guard()`:用 components.html 在父文件 capture 階段攔截,只在「非輸入框焦點 + 無修飾鍵」時
  吞掉 c / r;在欄位內打字完全不受影響。([app.py](app.py))
- **架構圖連線不直 / 斜線匯聚**:根因是應用層(app-layer)原本放在中欄內、把 pipeline-band 往下擠,導致
  左右欄(資料源 / 服務)與 pipeline 不同高 → 連線全斜。修法:把 **app-layer 抽成獨立全寬一列**,三欄
  (資料源 | 三代理人 | 服務)**頂部對齊**;左右欄改 `.dg-col`(flex 填高 + `space-between` 分散卡片),服務側
  鏡像資料源側改成 `svc → pipeline-band` 的 `matchY` 水平連線。**結果:5 條資料源 + 2 條服務 = 7 條全水平
  直線**,其餘 3 條(用戶→應用→pipeline→儲存)為短垂直層連線。([../flowchart-site/js/diagram.js](../flowchart-site/js/diagram.js))
- **直書「三代理人 Pipeline」看起來怪**:`.band-label` 由左側直書欄(`writing-mode: vertical-rl`,英文逐字
  堆疊)改成頂部**水平**標題列(`horizontal-tb`)。([../flowchart-site/css/diagram.css](../flowchart-site/css/diagram.css))

### Changed
- flowchart-site `index.html`:本地 css/js 加 `?v=20260609c` 快取破壞(改檔後瀏覽器才不會吃舊快取;之後
  再改檔請 bump 版本號 —— 先前驗證時就是被瀏覽器快取的舊 diagram.js 卡住、重啟 server 才更新)。

### Verification
- `node --check` diagram.js / `py_compile` app.py 綠。
- 瀏覽器(:8090 · 桌面寬 1600):三欄頂部對齊(569/569/569)、**7 條側連線 y-spread=0(全水平直)**、
  band 標題 `horizontal-tb`、0 console error。AppTest:封面載入 + 跑一次 0 例外、步驟①置中 wrapper 存在。
- ⚠ 架構圖三欄是 RWD:**視窗太窄(行動寬)會自動改單欄堆疊**(連線改走垂直),屬正常;要看「三欄水平直線」需桌面寬度。

---

## [2026-06-09] 「流程圖」視圖修復 + 對接去產品化(Agent Bot / 聊天平台)+ 3D 建模

### Fixed
- **「流程圖」視圖整片空白**([../flowchart-site/js/flowchart.js](../flowchart-site/js/flowchart.js)) — 上一版把 STEP
  id `push` 改名 `export`,但 `LINKS` 仍指向已不存在的 `push`(`store→push` / `push→done`),
  `stepById["push"]` 是 undefined → `build()` 在 drawArrows 拋錯 → 整個流程圖視圖空白。改成
  `store→export` / `export→done`。**這才是先前「按流程圖會卡住」的真正原因**(架構圖那次修的是另一個視圖)。

### Changed — 對接不再寫死特定產品
- **flowchart-site**:節點 `Hermes Agent` → **Agent Bot**、`Discord` → **聊天平台**(子標示 Discord / LINE /
  Slack 為例);DIAGRAM.services / demos 面板 / TAGS / EYEBROW / Pipeline 動畫文案全部去 Hermes/Discord
  字樣(Hermes / OpenClaw 僅作「範例」提及)。
- **app.py**:SECTION 10 標題「Hermes Discord Bot」→ **Agent Bot**;sidebar 提示、封面步驟①、隱私說明、
  ICD help、匯出 push_log 等**使用者可見字串**全部改通用;module docstring 同步。
  (實作 `hermes_skills/` / `hermes_export/` / `build_hermes_payload` 維持原名,作為 Hermes 範例實作 ——
   契約是一份 JSON,換任何會讀它的 bot 都行,不綁產品。)

### Added — 3D 場景建模(原為通用方塊)
- [../flowchart-site/js/scene.js](../flowchart-site/js/scene.js) 新增三種程序化 3D 模型:**Agent Bot**(機器人頭 +
  雙翼 + 天線 + 光環)、**聊天平台**(對話泡泡 + 打字三點 + 尾巴)、**資料匯出**(JSON 文件卡 + 內文線 +
  向外箭頭)。KIND 對應:hermes→bot / discord→chat / export→export(原本三者都是通用 server 方塊 / db)。

### Verification
- `node --check` 六個 flowchart JS 全綠;`py_compile` app.py 綠。
- 瀏覽器(:8090):**流程圖視圖** 14 box + 5 階段帶正常顯示、0 console error;**架構圖**節點標籤 =
  Agent Bot / 聊天平台、連線靜止單線;**3D 場景**切換後建模 0 error、三個新模型渲染(非方塊)、龍蝦
  吉祥物在 app 節點;Pipeline 跑到 100% 完成。

---

## [2026-06-09] 不再分五大族群 → 純個人化 + flowchart-site 修(卡頓 / 重疊線 / 恆動)

### Changed — 不再針對「五大敏感族群」,全面改個人化
- 封面步驟①**移除「健康狀況(五大族群多選)」**,改為「⚠ 我的 AQI 預警閾值」number_input
  (個人值;demo persona=60)。健康狀況改由 年齡 + ICD-10 已診斷疾病 + 病歷重點 表達。([app.py](app.py))
- **SECTION 08「🩺 你的個人化健康指數」**:從「每勾一個族群一張 safe_hours 卡」改成 **一張
  「針對你本人」的卡** —— 以你的 AQI 閾值為門檻算 safe_hours,並列出年齡 / BMI / 已診斷疾病
  為依據;**一定顯示**(不再需要先勾族群,根治上一版「過敏性鼻炎不在五類 → 卡片不出現」)。
- 分析師(B)prompt ②「敏感族群建議」→「健康建議」;預警員(C)本就依個人檔案逐城市生成。
  封面文案 / module docstring / `_persona_dict()`(移 conditions)/ 移除未用的 `SENSITIVE_GROUPS` import 同步。
- **flowchart-site**:advisor 節點步驟 老人/幼童/… → 讀個人檔案 / 風險分級 / 個人化建議 / 防護等級;
  advisor demo 面板從「5 族群 grid」改成「你的閾值 → 單一 safe_hours」即時試算;SECTIONS[07] /
  TAGS / STEPS / Pipeline 動畫文案去除「五大族群」字樣。

### Fixed — flowchart-site 架構圖
- **連線一直流動(恆動 / 「一直轉」)**:移除 `.conn-flow` 的 `dashflow` 無限動畫。原本每條線疊
  「靜態 base + 動態 flow」兩條 path,改成**單一靜態 base 線**,只在跑 Pipeline 時由 JS 加
  `.boost` 高亮當前資料流。([../flowchart-site/css/diagram.css](../flowchart-site/css/diagram.css)、[../flowchart-site/js/diagram.js](../flowchart-site/js/diagram.js))
- **連線重疊(重疊線)**:即上述兩條 path 疊一起的雙線感;移除 flow path 後變單線。
- **卡住**:11 條無限 SVG 動畫 + 滑鼠視差在大 DOM 上持續重繪 → 卡頓。移除動畫 + 視差幅度
  ±4.5/5.5 → ±2.0/2.4;Pipeline 進度條總步數修正(輸出 +2 → +3,先前會略為超過 100%)。

### Verification
- `py_compile` app/data 全綠;`node --check` 五個 flowchart JS 全綠。
- AppTest:封面載入本人檔案 → 跑**一次** → SECTION 08 顯示「你的個人化健康指數」**單卡**
  (無「容忍 AQI」族群卡)、健康狀況多選已移除、AQI 閾值 input 存在、0 例外。
- 瀏覽器(:8090)架構圖:`animatedConnPaths=0`、單線 11 條、advisor 步驟=個人化四步、
  advisor demo=個人版(0 族群卡)、Pipeline 跑到 100% 完成、0 console error。

---

## [2026-06-09] demo persona 改用本人資料(台中 · 19 · 過敏性鼻炎)

### Changed
- **封面 🎬 一鍵載入改成本人 persona**([app.py](app.py) `_render_persona_step1`)— 從原本的
  虛構「72 歲 COPD」改為使用者本人:台中市 / 19 歲 / 男 / 172cm·65kg(BMI 22.0) / 走路 /
  過敏性鼻炎(ICD-10 J30) / 病歷「空品差時鼻塞、眼睛癢」/ 個人 AQI 閾值 60。按鈕更名
  「🎬 載入我的檔案」。
- **demo 歷史資料重灌成台中**:`python scripts/seed_demo_data.py --city taichung`,讓
  SECTION 08 趨勢/比上週徽章、SECTION 09 散點對「台中」亮起(原本灌的是台北)。

### Note
- 使用者沒有勾五大快選敏感族群(過敏性鼻炎不在 老人/幼童/氣喘/心血管/孕婦 內),所以
  SECTION 08 的「🩺 個人化健康指數卡(safe_hours)」會顯示提示而非卡片;個人化改由
  分析師 / 預警員的 LLM 文字(含 J30 過敏性鼻炎)+ 城市趨勢 + Hermes 回覆呈現。demo 時想
  讓指數卡出現,在封面勾任一族群即可。

### Verification
- AppTest:封面按「🎬 載入我的檔案」→ 跑一次 Pipeline → 分析師 prompt 含「19 歲 / 過敏性鼻炎 /
  台中」、不含「72 歲」;0 例外;`latest_aqi.json` 的 user_profile age=19 / city=taichung /
  diagnoses=[過敏性鼻炎(J30)]。`read_export.py 台中市` 印出含「給 19 歲、過敏性鼻炎、BMI 22.0
  的提醒」。台中 demo:7 天趨勢 AQI 47–148、比上週 +70%、散點 r=+0.856。

---

## [2026-06-09] 架構轉換:推送(Webhook/Cron)→ 拉取(Hermes Discord Bot 讀 JSON 匯出)

把對外整合從「推送」改成「拉取」:不再用 Discord webhook、不再產生 cron 指令,改成 Pipeline
跑完匯出 `latest_aqi.json`、由 Hermes(Discord bot)**來這裡讀**。個人健康檔案移到封面
「步驟①」,分析師第一次跑就吃得到(根治需重跑問題)。SECTION 10 改成 Hermes Bot 說明 +
匯出狀態。flowchart-site 同步改為 push→pull。

### Added
- **`data.build_hermes_payload()`**([data.py](data.py)) — 純資料組裝,產生 Hermes 拉取用的
  JSON payload(`national` / `cities[20]` / `analyst_summary` / `advisories` / `user_profile` …)。
- **`_write_hermes_export()` + `_persona_dict()`**([app.py](app.py)) — Pipeline 末端把結果寫進
  `hermes_export/latest_aqi.json`(取代原 webhook 推送)。
- **`_render_persona_step1()` 封面個人健康檔案**([app.py](app.py)) — 個人設定(快選 + 進階
  檔案 + 🎬 demo 載入 + 清除)整段移到啟動 Pipeline「之前」的「步驟①」,所以第一次跑
  分析師 / 預警員就吃得到 persona,不必重跑。
- **`hermes_agents/aqi-reporter/`**(IDENTITY/SOUL/TOOLS/USER.md)+ **`hermes_skills/aqi-live/`**
  (SKILL.md + `read_export.py`)— Hermes Discord bot 人設 + 讀 `latest_aqi.json` 格式化 Discord
  回覆的 skill(支援指定城市 + 依 persona 個人化;`read_export.py [城市]` 可本機驗證,utf-8)。

### Changed
- **SECTION · 08 變純結果**([app.py](app.py)) — 移除所有輸入 widget(已移到封面),只留
  你的城市現況卡 / 個人化健康指數卡 / 7 天趨勢;頂端 caption 指回封面步驟①。
- **SECTION · 10 改成 Hermes Discord Bot**([app.py](app.py)) — 移除 cron 表單 / telegram·slack
  選項 / 「產生指令·立即註冊」按鈕;改顯示匯出狀態(最後匯出時間 / 城市數 / data_mode /
  是否含 persona)+ 設定說明 + 「Hermes 會回什麼」即時預覽。
- **sidebar** — 移除「對接後端」selectbox;改一行 Hermes 整合說明。
- **flowchart-site**([../flowchart-site/js/data.js](../flowchart-site/js/data.js) 等)— 架構模型
  push→pull:`openclaw` 節點改 `hermes`、`discord` relabel、新增 `export` 節點;邊改成
  advisor→export→hermes→discord(新 `pull` kind);DIAGRAM.services / SECTIONS / flows /
  features / MODELS 同步;diagram.js CONN、demos.js(discord/hermes/export 面板 + TAGS/EYEBROW)、
  flowchart.js STEPS、main.js Pipeline 動畫、index.html 圖例皆同步。

### Removed
- **Discord webhook 推送**:`data.send_discord_webhook()`、run_pipeline 內的 webhook 區塊、
  session key `discord_webhook_url`。
- **cron 產生 / 對接後端抽象**(上輪新增、本次已無用):`data.GATEWAY_BACKENDS` /
  `DEFAULT_GATEWAY` / `build_cron_command()` / `gateway_memory_path()`、SECTION 08
  「💾 同步至記憶體」按鈕、SECTION 10 cron 表單、`scripts/setup_cron.bat`、未用的
  `shlex` / `subprocess` import、session key `gateway_backend`。

> 保留:AgentAQI 品牌(早期名為 LobsterAQI · 龍蝦主題)、`openclaw_agents/` + `openclaw_skills/`(README 標為 legacy:在
> gateway 裡跑 agent + 正式 RAG,與推送/cron 無關)。

### Verification
- `py_compile` app / data / tsdb / seed_demo_data / read_export 全綠。
- **Streamlit AppTest**(stub 網路 + 攔截 `call_llm_api`):封面按 🎬 → 設 `_pipeline_should_run`
  跑一次 → 分析師 prompt 含「72 歲 / COPD」、**不含**「30 歲」(persona 第一次就生效);
  全頁 0 例外;`hermes_export/latest_aqi.json` 產生(20 城市 / analyst_summary / user_profile age=72)。
- `python hermes_skills/aqi-live/read_export.py 台北市` 印出含 persona 提醒的 Discord 回覆。
- demo 資料隔離(`source='demo'`)未受影響。

手動 checklist:
- [ ] 封面有「步驟① 個人健康檔案」+ 🎬 載入範例;SECTION 08 只剩結果(無輸入框)
- [ ] 填 persona → 跑「一次」 Pipeline → 分析師 / 預警員文字提到 72 歲 / COPD(不必重跑)
- [ ] SECTION 10 顯示「最後匯出 …」+ 預覽;`read_export.py` 跑得出內容
- [ ] flowchart-site 開得起來、無 console error;點 Hermes / 資料匯出 節點開出新面板;跑 Pipeline 動畫到「Hermes 讀 JSON 回答」
- [ ] 全專案 grep 無殘留 `send_discord_webhook` / `build_cron_command` / `gateway_backend`

---

## [2026-06-08] 修復:分析師永遠注入「年齡 30」(預設值誤判為已填)

### Fixed
- **分析師 / 預警員的 LLM prompt 永遠帶「年齡:30 歲」,看似讀不到 demo persona**([app.py](app.py))
  - 根因:`user_age` 預設值是 **30**(truthy),但 `_personal_profile_block()` 的「沒填就
    不注入」零回歸守衛是 `if not (age or diags or hist): return ""` —— age=30 永遠 truthy →
    守衛從不觸發 → 即使完全沒填,也把「年齡:30 歲」注入 prompt,`profile_filled` 也恆為
    True。上台時分析師會講「30 歲」,與 72 歲 COPD persona 對不上 → 容易被抓包。
  - 修法:
    - `user_age` 預設 30 → **0**(0 = 未提供);「🗑 清除個人健康資料」按鈕也改設 0。
    - `_personal_profile_block()` 年齡顯示改條件式(0 →「未提供」);守衛因此恢復正確:
      沒填(age=0 且無診斷 / 無病歷)→ 回空字串、完全不注入(真・零回歸)。
    - 年齡 number_input 加 help「0 = 不提供」;MEMORY.md 寫入同步顯示「未提供」。
    - 載入 demo persona 後新增提醒 caption + toast:分析師 / 預警員的「文字報告」需
      **重跑一次 Pipeline** 才會用新 persona(指數卡是即時的,但 LLM 報告是 Pipeline
      期間生成的)。
  - 結果:demo 流程 = 跑 Pipeline → 🎬 載入 persona → 再跑一次 Pipeline → 分析師據 72 歲
    COPD 分析,不再出現 30 歲。

### Verification
- Streamlit AppTest + 攔截 `data.call_llm_api` 擷取 prompt:
  - 未填:prompt **不含**「30 歲 / 年齡」,分析師只跑 1 次 LLM(預警員 C 正確跳過)。
  - 載入 demo persona:prompt **含**「72 歲 / COPD」、**不含**「30 歲」,分析師 + 預警員共 2 次 LLM。
  - 0 例外。

---

## [2026-06-08] 修復:demo 數據被 Pipeline 覆蓋 + AI 助理關閉殘留/延遲

接續同日「對接後端 + demo 灌庫」,修兩個實測發現的問題。

### Fixed
- **載入 demo 後重跑 Pipeline,demo 數據就不見了**
  - 根因:seed_demo_data 原本把 demo AQI 寫在 `source='cams_hourly'`,與真實 Pipeline
    的 CAMS 寫入**共用主鍵 `(ts, city_id, source)`** → 重跑 Pipeline 抓真實 CAMS 過去 7 天
    回填時 UPSERT 直接覆蓋掉 demo 的「污染事件軌跡」(7 天趨勢 / 比上週 +53% 徽章 /
    SECTION 09 散點全被洗成真實平緩值)。
  - 修法:把 demo 資料隔離到獨立的 **`source='demo'`**([seed_demo_data.py](scripts/seed_demo_data.py)),
    與真實 `cams_hourly` 完全不撞鍵;App 在儀表板閘門後偵測 `tsdb.has_demo_data()`,有 demo
    就自動改讀 demo source([app.py](app.py) 的 `_aqi_src` / `_diary_src`,套用到 SECTION 02
    比上週、本週紀錄板、SECTION 08 趨勢/徽章、SECTION 09 散點)。重跑 Pipeline 只動
    `cams_hourly`,demo 不受影響;`--clear` 後自動回讀真實資料(零回歸)。
  - 新增 `tsdb.has_demo_data(city_id=None)`、`tsdb.diary_with_aqi(..., source=...)`([tsdb.py](tsdb.py))。
  - SECTION 08 在 demo 模式顯示 caption「🎬 顯示預載 demo 數據」提示。
- **AI 助理聊天面板關閉有文字殘留 + 關閉延遲**([app.py](app.py))
  - 根因:✕ 關閉鈕用「回傳值 + `st.rerun()`」:點擊先觸發 fragment 自動重跑(此時
    `chat_expanded` 仍為 True → panel 連同捲動 iframe **又重畫一次**),handler 才設 False
    再 `st.rerun()` 切 FAB —— 兩次 fragment 執行 + panel 重畫造成文字殘留與延遲。
  - 修法:改用 `on_click` callback(`_set_chat_open` / `_set_chat_closed`):callback 在重跑
    「之前」就改好 `chat_expanded`,重跑時直接畫對的分支,只跑一次 rerun。FAB 開啟鈕一併改。

### Verification
- `py_compile` app/data/tsdb/seed 全綠;Streamlit AppTest 全頁渲染(demo source active)0 例外。
- **demo 隔離存活測試**:寫入 3380 筆模擬真實 `cams_hourly` 後,demo 的 7 天趨勢
  (AQI 24–148)/ 比上週 +53% / 散點 r=+0.856 **完全不變**(demo SURVIVED pipeline)。
- **聊天開關**:FAB 點擊 → 展開(panel + ✕);✕ 點擊 → 收合(FAB 回來),`chat_expanded`
  正確翻轉,0 例外。

手動 checklist:
- [ ] 跑 `seed_demo_data.py` → SECTION 08 看到趨勢 + 比上週徽章 + caption「🎬 顯示預載 demo 數據」
- [ ] 載入 demo persona → 重跑 Pipeline → SECTION 08/09 的 demo 內容**仍在**(不再被洗掉)
- [ ] `seed_demo_data.py --clear` → demo 內容消失,改顯示真實 cams_hourly(或空狀態提示)
- [ ] 開 AI 助理 → 按 ✕ → panel 立刻收掉、無文字殘留、無明顯延遲

---

## [2026-06-08] 對接後端可切換(OpenClaw 龍蝦 / Hermes)+ 期末 demo 假資料灌庫工具

把過去寫死的 OpenClaw(龍蝦)整合,抽成「可切換的對接後端」registry —— 現在
SECTION 10 的 cron 指令與 SECTION 08 的記憶體同步,都會跟著 sidebar 選的後端
(🦞 OpenClaw / 🪽 Hermes)動態改變 CLI 名稱與 MEMORY.md 路徑。Hermes 目前為
**實驗性佔位**(指令/路徑對稱複製 OpenClaw 慣例,待接上實際 Hermes CLI 再校正,
只需改 `data.build_cron_command()` 一處)。另外新增期末 demo 用的假資料灌庫工具,
讓 SECTION 08-10 一打開就有豐富內容可秀。

### Added
- **對接後端 registry `GATEWAY_BACKENDS` + `DEFAULT_GATEWAY`**([data.py](data.py)) — 仿
  `LLM_PROVIDERS` 的可擴充字典,每筆含 `name / cli / memory_root / workspace / docs /
  experimental`。內建 `openclaw`(真值)與 `hermes`(實驗性佔位)。
- **`gateway_memory_path(backend_id, agent_id)`**([data.py](data.py)) — 回傳該後端 +
  agent 的 MEMORY.md 路徑(`<root>/<id>/agent/MEMORY.md`,`~` 自動展開);不認得的
  backend_id 安全 fallback 到 OpenClaw。
- **`build_cron_command(backend_id, ...)`**([data.py](data.py)) — 集中組裝 `<cli> cron
  add ...` argv;將來換後端只改這一個函式,UI 與呼叫端不動。
- **sidebar「進階整合 · 對接後端」selectbox**([app.py](app.py)) — 在 LLM 提供商之下,
  可切 🦞 OpenClaw / 🪽 Hermes;選實驗性後端會顯示 ⚠ 佔位提醒。新增 session_state
  `gateway_backend`(預設 `DEFAULT_GATEWAY`)。
- **SECTION · 08「🎬 載入 demo 範例檔案」按鈕**([app.py](app.py)) — 一鍵把個人設定填成
  寫實的「72 歲 · COPD(J44)+ 高血壓(I10)· BMI 29.4」persona(城市台北、狀況老人
  + 心血管、病歷重點),並自動展開進階健康檔案 expander。實作用「設鏡像欄位 + pop
  widget key」逼 widget 重新初始化,跨 Streamlit 版本穩定、無警告。
- **`scripts/seed_demo_data.py` + `scripts/seed_demo_data.bat`**(新檔) — 期末 demo 假
  資料灌庫:① 過去 16 天 × 每小時 × 20 城市 AQI 歷史 ② 常駐城市 14 天「污染事件
  軌跡」(本週均值明顯高於上週)③ 14 天健康日誌(症狀由同一軌跡推導 → 正相關)。
  全部標記 `data_mode='demo'` / note 含 `[demo]`,可 `--clear` 一鍵移除,不污染真實
  資料。`--city <id>` 可換常駐城市。
- **`docs/demo_guide.md`**(新檔) — 「個人化推薦以後(SECTION 08-10)」的期末 demo 逐段
  講稿 + 事前準備 + Hermes/OpenClaw 切換亮點 + 無 LLM key 的 fallback 說法。

### Changed
- **SECTION · 08 記憶體同步改讀選定後端**([app.py](app.py)) — 按鈕標題、寫入路徑、成功
  訊息從寫死的 `OpenClaw` / `~/.openclaw/...` 改為 `gateway_memory_path()` + 後端
  `name`。privacy 提示同步動態化(順手補上原本漏掉的 `/agent/` 路徑段)。
- **SECTION · 08「🗑 清除個人健康資料」按鈕強化**([app.py](app.py)) — 除了重設鏡像
  欄位,額外 pop 進階欄位的 widget key 並解除 `demo_profile_loaded`,確保某些
  Streamlit 版本下欄位也能確實視覺重置(同時收合 expander)。
- **SECTION · 10 cron 產生改用 `build_cron_command()`**([app.py](app.py)) — section-sub
  文字、「複製到 terminal」提示中的 `cron list` 指令前綴,皆隨選定後端動態改變
  (龍蝦 `openclaw` / Hermes `hermes`)。
- **module docstring 與區段註解**([app.py](app.py)) — SECTION 10 描述從「OpenClaw cron」
  改為「對接後端(OpenClaw 龍蝦 / Hermes)cron」;cron 區段註解標明 CLI/旗標集中在
  `data.build_cron_command()`。

### Verification
```powershell
cd <project>
python -m py_compile app.py data.py tsdb.py scripts/seed_demo_data.py   # 全綠
python scripts/seed_demo_data.py        # 灌 demo 資料(可加 --clear / --city)
```
- **py_compile**:app.py / data.py / tsdb.py / seed_demo_data.py 全部通過。
- **Streamlit AppTest 無頭跑全頁**:預設開機 0 例外、sidebar 出現「Agent Gateway」
  選擇器;模擬 `pipeline_done` + 假快照後 SECTION 02-10 全渲染 0 例外。
- **demo 載入 / 清除按鈕**:點「🎬 載入 demo 範例」→ age=72 / sex=male / BMI 來源
  168cm·83kg / dx=[J44,I10] / demo_flag=True;點「🗑 清除」→ 全部回預設、flag=False。
- **後端切換**:`gateway_backend='hermes'` → 記憶體同步按鈕變「💾 同步至 🪽 Hermes
  Agent(實驗性) 記憶體」、privacy 顯示 `~/.hermes`、SECTION 10 sub 顯示 Hermes cron。
- **demo 資料品質**(台北):比上週 **+53%**(this 85.6 / prev 55.9)、7 天趨勢 AQI
  16–148、SECTION 09 配對 14 筆 **Pearson r = +0.856**(明顯正相關且非 1.0)。

手動 checklist:
- [ ] sidebar 切「🪽 Hermes」→ 出現實驗性 ⚠ 提醒;SECTION 10 產生的指令第一個字是 `hermes`
- [ ] 切回「🦞 OpenClaw」→ 指令第一個字是 `openclaw`、記憶體路徑回 `~/.openclaw`
- [ ] SECTION 08 按「🎬 載入 demo 範例」→ 進階檔案自動展開、個人化指數卡出現 72 歲/心血管
- [ ] 先跑 `seed_demo_data.py` → SECTION 08 有 7 天趨勢 + 比上週徽章、SECTION 09 散點有趨勢線
- [ ] `seed_demo_data.py --clear` → SECTION 08/09 的 demo 內容消失,真實資料(若有)不受影響

---

## [2026-05-26] 預警員個人化建議超時修復:timeout 25s → 120s

### Fixed
- **預警員(Agent C)生成 20 城市個人化建議逾時**([app.py:865](app.py)) — Agent C 需為每個城市輸出 3-4 句個人化建議,`max_tokens=6144` 本身夠大,但 `timeout=25` 秒在長輸出時根本來不及等 LLM 生成完就斷了。修復:
  - `_agent_llm` 的 `timeout=25` → `timeout=120`
  - 20 城市 × ~300 token/城市 = ~6000 token,Claude 生成時間約 60-90 秒,120 秒綽綽有餘
  - 分析師(Agent B)因回應較短,維持 25 秒 timeout 不變

---

## [2026-05-21] 個人訂閱按鈕重構:將「產生指令」Form 與「直接註冊」按鈕脫鉤 (by Einosensokami)

### Fixed
- **app.py SECTION · 10「直接幫我註冊」按鈕無回應**([app.py:3579-3663](app.py)) — 原設計把「產生指令」form submit 與「直接幫我註冊」按鈕寫在同一個 `if sub_submit:` 區塊，導致按鈕 callback 在 form submit 的同一 script run 內被評估，Streamlit 認為 button return value 在 form context 內無效而不執行後續邏輯。修復：
  - form submit 只負責將命令寫入 `session_state["_sub_cmd"]`，不直接渲染 UI
  - 指令顯示 + 兩個 action button 移到獨立的 `if st.session_state.get("_sub_cmd_str"):` 區塊，完全脫離 form submit 上下文
  - 從此按鈕點擊可正確觸發 `subprocess.run(openclaw cron add ...)` 並顯示成功/失敗訊息
- **按鈕寬度一致** — 同步拿掉 `type="primary"` 使兩個按鈕視覺一致。

---

## [2026-05-20] Bug 修復:button width 參數 + 健康日誌 avg_aqi 數值型別 (by Einosensokami)

### Fixed
- **app.py `st.button` 不支援 `width='stretch'`**([app.py:2617](app.py)) — `ButtonMixin.button()` 收到未知參數 `width`,拋出 `TypeError`。移除该參數,按鈕寬度由 `st.columns` 容器自動控制。
- **app.py 健康日誌 `_display_df["avg_aqi"].round(1)` 型別錯誤**([app.py:3134](app.py)) — `round()` 要求數值型別,傳入 `object` _dtype 導致 `TypeError: Expected numeric dtype, got object instead`。改用 `pd.to_numeric(..., errors="coerce")` 先轉型再 round,同步修復 `peak_aqi` 欄位。

---

## [2026-05-20] SECTION · 08 個人化推薦 — RAG 個人化升級(雙管齊下)

回應使用者質疑「為甚麼是這五大群?這樣真的有個人化部分嗎?」 — 五大群是 UI 入口的快速 selection,不是個人化的全部。升級後,使用者可在進階檔案填入「年齡 / 性別 / BMI / 已診斷疾病(ICD-10)/ 病歷重點 / 個人病歷文件」,這些資料會注入 LLM prompt + 進入 RAG(personal scope 享 1.4× 加權),讓 AI 助理 / 分析師 / 預警員給專屬建議。**現有公式 `safe_hours` 刻意不動** — 公式給快速量化指標,LLM 給為什麼。

### Added
- **`USER_ICD10_OPTIONS` 常數**([data.py:383-400](data.py)) — 12 項與空氣污染高關聯的 ICD-10:氣喘 J45 / COPD J44 / 慢性支氣管炎 J42-J43 / 過敏性鼻炎 J30 / 高血壓 I10 / 冠心症 I20-I25 / 心律不整 I48 / 心衰 I50 / 第二型糖尿病 E11 / 失智 F03 / 懷孕 Z33 / 肺癌 C34。
- **`_ingest_personal_medical_file()`**([app.py:387-411](app.py)) — wrapper 包裝既有 `_ingest_uploaded_file`,把上傳結果標 `scope="personal"`、source 前綴 `[個人病歷]`、並寫入 `user_med_files` metadata。
- **`_calc_bmi()` + `_personal_profile_block()`**([app.py:1471-1599](app.py)) — 兩個 helper:BMI 用 WHO 標準分類;profile_block 拼裝給 LLM 的 prompt 注入段落,**使用者完全沒填時回空字串**(零回歸保證)。
- **SECTION · 08 進階個人健康檔案 expander**([app.py:2934-3057](app.py)) — 在既有三個 selectbox 之後新增 `st.expander`,內含:隱私警語 / 年齡 / 性別 / 身高 / 體重(BMI 即時) / ICD-10 multiselect / 病歷重點 text_area / 個人病歷檔上傳(PDF / TXT / MD)/ 清除按鈕。
- **session_state 新增 7 個 key**([app.py:185-194](app.py)) — `user_age` / `user_sex` / `user_height_cm` / `user_weight_kg` / `user_diagnoses` / `user_med_history` / `user_med_files`。

### Changed
- **RAG chunk schema 從 `{source, text, page}` → `{source, text, page, scope}`** — `scope` 為 `"global"`(預植入 + sidebar 上傳的通用文獻)或 `"personal"`(個人病歷)。`_seed_rag_chunks`([app.py:319-336](app.py)) 與 `_ingest_uploaded_file`([app.py:339-385](app.py)) 都補 `scope="global"`。
- **`retrieve_rag_chunks()`**([app.py:413-447](app.py)) — 對 `scope=="personal"` 的 chunk 乘 `PERSONAL_BOOST = 1.4`,讓個人病歷在檢索時優先被命中。fallback(全 miss 回 starter)行為不變。
- **`_build_chat_context()`**([app.py:1602-1650](app.py)) — 在「各 agent 分析摘要」之前注入 `_personal_profile_block()`,使用者沒填時為空(零回歸)。
- **AI 助理 `full_prompt`**([app.py:1707-1718](app.py)) — rag_block 之後追加一句:「若上方有『使用者個人健康檔案』段落,請在建議中明確提及該因素(年齡 / BMI / 已診斷疾病 / 病歷重點)如何影響此使用者的個人風險」。
- **Pipeline 分析師(B) `_agent_llm` prompt**([app.py:902-928](app.py)) — prompt 字串前插入 `_personal_profile_block()`;第 ② 段請 LLM 對「使用者本人」(年齡 / BMI / 已診斷)給 1-2 句量身建議。
- **Pipeline 預警員(C) `_agent_llm` prompt**([app.py:960-989](app.py)) — 同上,額外請 LLM 在 5 大群建議後附加「🩺 給你本人的建議」段落,依年齡 + ICD-10 + 病歷重點給 2-3 句具體建議。
- **MEMORY.md 寫入內容**([app.py:3071-3097](app.py)) — 從原本 3 欄(城市 / 健康狀況 / 活動)擴充為 5 區塊(基本資料 / 常駐城市與活動 / ICD-10 / 病歷重點 / 已上傳病歷文件),寫入路徑(`~/.openclaw/agents/{analyst,advisor}/agent/MEMORY.md`)不變。

### Privacy
- expander 內固定顯示 `st.info` 隱私警語:資料寫本機 MEMORY.md(純文字未加密)+ 送雲端 LLM API(使用者自己設定的 key),**不傳給專案作者或任何第三方**。
- 新增「🗑 清除個人健康資料」按鈕:一鍵 reset 7 個 user_* 欄位 + 從 `rag_chunks` 移除所有 `scope=="personal"` 的 chunks。

### Unchanged(刻意保留)
- **`safe_hours` 公式**([app.py:3013](app.py)) — 仍為 `max(0, 12 - (current_aqi - GROUP_AQI_LIMIT[gid]) × 0.15)`,不依年齡 / BMI / 疾病微調。理由:避免「為何 BMI>30 扣 5 點」這類無實證的 magic number 引來同一質疑;個人化全部發生在 LLM prompt 端。
- **既有三個 selectbox(城市 / 活動 / 健康狀況)** — 維持原欄位,新欄位放 expander 內,避免一次資訊過載。
- **Retrieval 演算法** — 仍是 2-char n-gram 字元重疊(無依賴、跨中英文),只多了 personal boost 加權,沒改基礎演算法。

### Verification
```powershell
cd C:\Users\tunai\Downloads\aqi-tw-personal-main
.venv\Scripts\python.exe -m py_compile app.py data.py
streamlit run app.py
```

手動測試 checklist:
1. **零回歸**:不展開新 expander → SECTION · 08 與 AI 助理輸出與升級前 100% 一致
2. **個人 profile 注入**:展開 expander,填年齡=72 / BMI=29.4 / 勾「COPD」「高血壓」 / 病歷寫「2020 確診 COPD GOLD II 級」→ 跑 Pipeline → 預警員(C)輸出應**明確提及 72 歲 / COPD / 高血壓**,並有「🩺 給你本人的建議」段落
3. **個人病歷 RAG**:上傳一份假病歷 TXT → 開 AI 助理問「我的肺功能允許做什麼運動」→ 「📚 引用 RAG」抽屜應含該病歷 chunk(1.4× 加權命中)
4. **MEMORY.md**:按「💾 同步」→ 開 `~/.openclaw/agents/analyst/agent/MEMORY.md` 應見 5 區塊(基本資料 / 常駐城市與活動 / ICD-10 / 病歷重點 / 已上傳文件)
5. **清除按鈕**:按「🗑 清除個人健康資料」→ 7 個欄位回預設 + `rag_chunks` 中 personal 條目消失
6. **公式未變**:SECTION · 08 個人化健康指數卡的 `safe_hours` 數字與升級前完全相同
7. **無 LLM key fallback**:清空 sidebar 的 LLM key → 跑 Pipeline → cards 仍正常顯示,不因 profile 注入而 crash

---

## [2026-05-15 後續] AI 助理修兩個 bug:輸入框釘底 + 回應截斷偵測

### Fixed
- **聊天輸入框未常駐底部**([styles.py:1016-1052](styles.py)) — 之前用 `margin-top: auto + flex-shrink: 0 + order: 99` 的方案理論上可行,但實測無效。根因是 Streamlit 在 `.st-key-floating_chat` 與 `[data-testid="stChatInput"]` 之間插了 `stVerticalBlockBorderWrapper` 等包裝元素,flex 屬性無法跨層 propagate。**改用 `position: absolute` 直接以 panel 為定位錨點**(panel 已是 `position: fixed`,提供 positioning context),輸入框 `bottom: 14px / left: 16px / right: 16px` 永遠釘底。chat_history 加 `padding-bottom: 64px` 預留輸入框空間。
- **LLM 回應「話講一半就停」**([app.py:1683-1693](app.py)、[data.py:1546-1555](data.py)、[data.py:1583-1596](data.py)) — 兩個原因疊加:
  - **a) max_tokens 上限太低** — 原 `max_tokens=4096`,Claude 達上限後直接截斷在句子中間,而舊 `call_llm_api` **未偵測 stop_reason='max_tokens'**,使用者完全看不出是被截掉的。
  - **b) timeout 太短** — 原 `timeout=25`,長回應的生成可能需要 30-40s,容易在中途逾時返回 None(顯示 fallback 摘要)。
  - **修法**:聊天 max_tokens → 8192、timeout → 60s;同時在 `call_llm_api` 偵測 Anthropic `stop_reason=='max_tokens'` 與 OpenAI 格式 `finish_reason=='length'`,截斷時自動附加「⚠ 回應達 max_tokens 上限,可能未完整 — 可追問細節或調高設定」標示。
---

## [2026-05-16] 全面審查

### Fixed
- **app.py module docstring**([app.py:11-22](app.py)) — SECTION 列表只有 01/02/03/09/10,補完 04-08(污染物剖析 / 環境關聯 / 官民比較 / 健康預警 / 個人化推薦)
- **app.py 封面區 SECTION 順序註解**([app.py:1747-1749](app.py)) — 原寫「→ 02 → 03 ... 04 (訂閱)」完全錯誤(04 是污染物剖析,訂閱是 10)。改為正確的 01→10 順序
- **app.py 封面 cover-subtitle HTML**([app.py:1782-1784](app.py)) — 仍寫「並由 Critic 自動審稿」,但 Critic 已於 3-agent 重構時移除。改為「由分析師整合 RAG 文獻,預警員給出敏感族群建議」
- **app.py 城市深入 modal 註解**([app.py:2173-2176](app.py)) — 提及已刪的 `pages/1_城市深入.py for direct URL access`,改為歷史備註
- **app.py SECTION · 09 標頭註解**([app.py:3003-3005](app.py)) — 原「SECTION · 09(舊編號)→ 移至下方;這裡先放健康日誌」語意混亂,簡化為直接的 SECTION · 09 標頭
- **app.py SECTION · 07 預警卡 fallback**([app.py:2665-2672](app.py)) — 加入 `user_conditions` fallback:若使用者在 SECTION · 08 已選個人健康狀況但 SECTION · 07 沒按篩選按鈕,預設用 user_conditions 展開(避免一次列出全部 5 個族群造成資訊過載)
- **tsdb.py `upsert_diary_entry` `created_at` 語意**([tsdb.py:489-528](tsdb.py)) — 原本 `INSERT OR REPLACE` 會把同一筆 (date, city_id) 整列覆寫,導致 `created_at` 變成「最後更新時間」而非「首次建立時間」。改為先 SELECT 既有 created_at,後續 upsert 沿用首次的值
- **README.md 嚴重過時**(多處) — 全面重寫:
  - 「為何只剩 3 個 agent」段落補上「scraper/ 與 critic/ 已於 2026-05-13 移除」
  - 整段「Multi-page 結構」(原描述 pages/1_城市深入、2_城市並排比較、3_個人訂閱)改寫為「單頁 10 個 SECTION + 城市深入 modal + 浮動 AI 助理」
  - 「scraper/ 與 critic/ 兩個資料夾保留下來」→「已於 2026-05-13 移除」
  - 「進入 3_個人訂閱分頁」→「主畫面捲到 SECTION · 10 個人訂閱」(順便補上 Digest / Alert 兩種模式說明)
  - 「9 大儀表板 section」→「10 個 SECTION」
  - 架構圖底部 `subprocess → openclaw CLI` → `shell → scripts/setup_cron.bat → openclaw cron`
  - **整個檔案結構圖重寫**:移除 `openclaw_client.py`、`pages/`、`openclaw_agents/{scraper, critic}/`(都不存在);新增 `tsdb.py`、`_city_detail.py`、`CHANGELOG.md`、`.gitignore`(實際存在但漏列)

### Removed
- **app.py SECTION · 08「未來 12 小時最佳外出時段」整欄** — `best_outdoor_hours()` 用 `np.random` 合成預測,並非真實資料,容易誤導使用者出門決策。與 `_city_detail.py:215-219` 同一理由(該檔已於 2026-05-13 移除)。具體:
  - import `best_outdoor_hours`、`make_outdoor_bars`([app.py:55, 78](app.py))
  - `with per2:` 整段卡片渲染(原 ~32 行)
  - `per1, per2 = st.columns([2, 3])` 改為 `per1 = st.container()`,SECTION · 08 改為單欄全寬呈現
- **app.py `show_chat` session_state 欄位**([app.py:186](app.py)) — 自標 `# 已不使用(legacy)`,grep 確認全檔無其他使用
- **app.py `openclaw_agent_map` 中的 `scraper` / `critic` 鍵**([app.py:141-147](app.py)) — 與 3-agent 設計一致(同檔 L608、L670、L979 早已明示這兩個 agent 已刪)
- **data.py `best_outdoor_hours` 整個函式**(~36 行) — app.py / _city_detail.py 都已不呼叫,連帶死碼
- **data.py `_open_meteo_city_slice`**(~18 行) — 註解自標「目前已無呼叫者」
- **data.py `fetch_lass_airbox = fetch_citizen_sensors` 別名**(3 行) — 註解自標「呼叫端遷移就刪」,app.py 確認已全用新名
- **data.py module docstring 與 CleaningReport docstring** 對應地刪除 `best_outdoor_hours` / `fetch_lass_airbox` 條目
- **charts.py `make_outdoor_bars`**(~28 行 + section 標頭)— 唯一呼叫者(app.py SECTION · 08)已移除

### Verification
```powershell
cd C:\Users\tunai\Downloads\aqi-tw-personal-main
.venv\Scripts\python.exe -m py_compile app.py styles.py data.py tsdb.py charts.py _city_detail.py
streamlit run app.py
```
功能測試清單:
- [ ] 右下角開啟聊天面板 → 輸入框永遠在最底(對話有 0、1、5、20 則訊息都測試)
- [ ] 拉長視窗 / 縮小視窗 → 輸入框跟著 panel 底邊
- [ ] 問一個複雜問題(如「5 類敏感族群的詳細運動建議」)→ 回應完整,即使超過原 4096 token 也不截斷
- [ ] 若不幸還是達到 8192 上限 → 訊息末尾應有「⚠ 回應達 max_tokens 上限」提示
- [ ] 連續發 5 則訊息 → input 永遠可用、永遠在底
.venv\Scripts\python.exe -m py_compile app.py tsdb.py charts.py styles.py _city_detail.py data.py
.venv\Scripts\Activate.ps1
streamlit run app.py
```
功能驗證 checklist:
- [ ] py_compile 全綠
- [ ] 主畫面跑 Pipeline 正常,SECTION · 01-10 全部渲染
- [ ] **封面 cover-subtitle 不再提「Critic 自動審稿」**,改為「分析師 + 預警員」
- [ ] **SECTION · 08「個人化推薦」只剩單欄(全寬)** — 沒有「未來 12 小時最佳外出時段」整欄
- [ ] **SECTION · 07** 在 SECTION · 08 已勾「老人 + 氣喘」後,預警卡 expander 展開只顯示這兩族群(不是全部 5 個)
- [ ] **SECTION · 09 健康日誌** 同一天打卡兩次,SQLite `SELECT created_at FROM health_diary WHERE date='YYYY-MM-DD'` 應為**第一次**寫入的時間
- [ ] **城市深入 modal** 仍可開啟,內容正常
- [ ] **README 結構圖** 與實際 `ls` 完全一致:沒有 `pages/`、`scraper/`、`critic/`、`openclaw_client.py`;有 `tsdb.py`、`_city_detail.py`、`CHANGELOG.md`

### 資料夾命名審查結果
全部 ✓ — 已透過讀 IDENTITY.md / SKILL.md / .bat 確認:
- `openclaw_agents/{advisor, analyst, collector}` 三個子目錄都符合 3-agent 角色
- `openclaw_skills/aqi-knowledge` 內容為 WHO/EPA/Lancet/MOENV 文獻索引
- `scripts/{build_knowledge.bat, setup_cron.bat}` 名稱即功能
- `docs/`、`.streamlit/` 為慣例命名,合理

---

## [2026-05-15] 健康管理擴充:P1 四項 + 每日 Digest 推送 + 修 SECTION 編號 bug

### Fixed
- **SECTION 編號重複 bug**([app.py:16](app.py)、[app.py:2828](app.py))— 原本「污染物剖析」與「個人訂閱」都標 SECTION · 04。修正為:污染物 04 / 環境 05 / 資料源 06 / 健康 07 / 個人化 08 / **健康日誌 09(新)** / 個人訂閱 10。module docstring 同步更新。

### Added

#### 🔴 P1 #1 · 個人 AQI 預警閾值 ([app.py:142](app.py)、[app.py:1102](app.py)、[app.py:2090](app.py))
- 新增 session_state `user_aqi_threshold`(預設 100)
- sidebar slider 讓使用者設定 50-200 範圍
- 主儀表板(SECTION · 02)在「時間軸 + 資料新鮮度」之下新增**個人 AQI 預警橫幅**:
  - 突破閾值 → 紅色發光橫幅「⚠ 你的城市突破預警閾值」+ AQI 值 + 等級
  - 未突破 → 淡色資訊條,顯示城市現況 + 預警閾值
- 顯眼度依據:警告色 `#ff4757` + box-shadow + 左側 4px 邊框

#### 🔴 P1 #4 · 歷史對比 highlight(整合於上述橫幅)
- 用現有 `tsdb.city_period_avg(city, 168h)` 計算「本週 vs 上週」平均 AQI
- 顯示徽章:↑ 比上週 +X% (橘) / ↓ 比上週 -Y% (綠) / ≈ 與上週相當(灰)
- 即使未突破閾值也會顯示,讓使用者一眼看出趨勢

#### 🔴 P1 #3 · 個人化敏感族群指數卡 ([app.py:2865](app.py))
- SECTION · 08 個人化推薦底部新增「🩺 你的個人化健康指數」區塊
- 對使用者勾選的**每個敏感族群**單獨計算:
  - 容忍 AQI 門檻表:`elderly=60, children=70, asthma=50, cardiovascular=60, pregnant=50`
  - safe_hours = max(0, 12 - max(0, AQI - limit) × 0.15)
  - 4 級防護建議:✓ 正常 / 🧣 一般口罩 / 😷 N95 / 🚫 室內為主
- 卡片網格:每個族群一張卡,顯示時數 + 防護建議,顏色依嚴重度
- 未勾選任何族群 → 顯示 nudge 提示去 sidebar 設定

#### 🔴 P1 #2 · 健康日誌(新 SECTION · 09)([app.py:3002](app.py)、[tsdb.py:354](tsdb.py))
- **新 SQLite table `health_diary`**(tsdb.py):`(date, city_id, symptom_score, outdoor_min, note, created_at)` 複合 PK
- **新 tsdb 函式**:
  - `upsert_diary_entry()` — 同一天同城市可覆蓋
  - `read_diary(city_id, days=30)` — 讀最近 N 天
  - `diary_with_aqi(city_id, days=30)` — JOIN aqi_snapshots 帶入該日 cams_hourly 平均
- **UI**:
  - 左欄今日打卡表單:症狀分數 slider 0-5、戶外分鐘 number_input、備註 text_input
  - 預載當日已有的紀錄(可修改而非每次重填)
  - 右欄 30 天散點圖:x = 平均 AQI、y = 症狀分數、bubble 大小 = 戶外分鐘、顏色依症狀
  - ≥ 3 筆配對資料時自動計算 Pearson r + 趨勢線 + 中文解讀("✓ 對空污較敏感" / "≈ 弱相關" 等)
  - 摺疊區顯示原始打卡紀錄表

#### 🟡 P2 #7 · 每日 Digest 推送(擴充 SECTION · 10 個人訂閱)([app.py:3186](app.py))
- 個人訂閱表單新增 **推送模式** radio:
  - **📅 每日 Digest**(預設) — 每天固定時段推完整摘要(空品速覽 + 6h 預測 + 族群建議 + 警示時段)
  - **⚠ 即時預警** — 只在 AQI 突破閾值時推單條警示
- 不同模式有不同 cron 頻率預設選項:
  - Digest:每天 7 點 / 8 點 / 7+18 點 / 週一三五 7 點
  - Alert:每小時 / 每 30 分鐘 / 每 2 小時 / 8+18 點
- LLM prompt 動態組裝:Digest 模式產出 4 段結構化摘要(🌅 速覽 / 🕐 預測 / 🏥 建議 / ⚠ 注意);Alert 模式維持原本 2 段
- Cron job 命名 prefix 區分:`AgentAQI-digest-{city}` vs `AgentAQI-alert-{city}-{threshold}`

### Verification
```powershell
cd C:\Users\tunai\Downloads\aqi-tw-personal-main
.venv\Scripts\python.exe -m py_compile app.py tsdb.py charts.py styles.py _city_detail.py data.py
.venv\Scripts\Activate.ps1
streamlit run app.py
```
功能驗證清單:
- [ ] sidebar 「個人 AQI 預警」slider 出現,預設 100
- [ ] 主儀表板:你的城市 AQI > 閾值 → 紅色橫幅;< 閾值 → 淡色資訊條;旁邊都有「比上週 ±X%」徽章
- [ ] SECTION · 08 底部:勾選「老人 + 氣喘」→ 出現 2 張個人化指數卡顯示 safe_hours
- [ ] SECTION · 09:今日打卡表單儲存後出現 success;隔天打卡可覆蓋
- [ ] 連續打卡 3 天以上 → 右側出現散點圖 + Pearson r 解讀
- [ ] SECTION · 10:切換 Digest 模式時,「推送頻率」選項變成每日 7 點等;產生的指令含 `--name AgentAQI-digest-...`

### 健康功能比例變化
- 之前:1/9 真正個人化(SECTION · 08 個人化推薦)= **11%**
- 現在:4 個顯眼個人化區塊(主畫面預警橫幅、SECTION · 08 個人化指數卡、SECTION · 09 健康日誌、SECTION · 10 Digest 模式)
- 個人化 / 健康相關功能整體佔比 ≈ **30-35%**(視覺空間)

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
- [ ] 主畫面 sidebar 左側只有 AgentAQI 一個 app,沒有 城市深入 / 城市並排比較 / 個人訂閱 三個分頁
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
