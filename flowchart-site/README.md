# 🦞 LobsterAQI — 架構流程圖網站

把 [aqi-tw-personal](https://github.com/Tunai-0511/aqi-tw-personal)（LobsterAQI 台灣空品多代理人監控平台）的**真實架構與資料流**做成一個可互動的流程圖網站，右上角可切換兩種視圖：

### 🗺 架構圖（預設）
比照分層架構圖：**用戶層 / 應用層 / 外部資料源 / 三代理人 Pipeline / 外部服務 / 儲存層**。每個 agent 卡片含子步驟（資料擷取→清洗→整合→品質檢查）與輸出清單；節點間有四種**資料流動畫**（即時 / LLM 呼叫 / 通知排程 / 儲存）。滑鼠移動時整張圖會 3D 視差傾斜，卡片懸停浮起。

### 🌐 3D 場景（電影感模型）
真正的 3D 模型場景：代理人 = 旋轉核心 + 光環、資料源 = 伺服器方塊、RAG/LLM = 線框 AI 腦、SQLite = 資料庫圓柱…，霓虹 bloom 發光（弱 GPU 會自動關閉退回一般渲染）。可左鍵拖曳旋轉、右鍵（或 Shift+左鍵）拖曳平移整個畫面、滾輪縮放。**跑 Pipeline 時，帶訊息的資料封包會沿光束在節點間飛行 → 看得到代理人之間的流程溝通。**

### ▶ 跑一次 Pipeline（兩視圖共用）
重現 `run_pipeline()`，頂部有**進度步驟器**：`① 採集者 ▸ ② 分析師 ▸ ③ 預警員` + 當前子步驟 + 進度條，清楚顯示「做到哪一步」；架構圖會逐一點亮 agent 與子步驟、3D 場景會逐一點亮節點，右下角同步通訊日誌。

- **點開看實際流程 demo**：點任一卡片 / 節點，右側面板會跑該環節的**真實流程動畫** —
  - **採集者**：EPA 20 城市即時抓取 + 民間感測器清洗計數（原始→保留→丟棄）
  - **分析師**：加權風險公式 + RAG 文獻檢索評分 + LLM 逐字生成 3 段報告
  - **預警員**：5 類敏感族群的 `safe_hours` 試算（含情境 AQI 滑桿）
  - **RAG**：**向量空間最近鄰檢索視覺化** — 知識庫文件投影在 2D 語意空間，查詢「嵌入」後畫出 kNN 連線、cosine 相似度、個人病歷 ×1.4 加權
  - 其餘節點：對齊原始碼的端點、schema、參數說明
- **一鍵跑 Pipeline**：重現 `run_pipeline()` 的逐節點點亮 + 通訊日誌。

> demo 用的城市清單、AQI 分級色、加權公式、RAG 文獻、`safe_hours` 公式都直接取自專案原始碼（`data.py` / `app.py`），數值會依「當下小時」用專案的日夜雙峰 × 城市偏差模型即時產生。

## 怎麼開

**直接雙擊 `index.html` —— 就這樣，完整可跑。**

所有 3D 模型（無人機、龍蝦、衛星、監測塔、感測器）都已**內嵌進網頁**（base64），`file://` 也能載入，**不需要伺服器、不需要 localhost**。架構圖、3D 場景、Pipeline、循環、所有 demo 全部正常運作、完全離線。

> 之前「localhost 拒絕連線」是因為去連了一個**沒在跑的伺服器**。現在不用了 —— 直接打開 `index.html` 即可。
> `start.bat`（本機伺服器）仍保留，但只有當你要載入「自己新增、未內嵌」的 `.glb` 模型時才需要。

## 操作

| 動作 | 說明 |
|------|------|
| 🗺 架構圖 / 🌐 3D 場景 | 右上角切換兩種視圖 |
| 點卡片 / 節點 | 開啟該環節的實際流程 demo |
| 滑鼠移動（架構圖）| 整張圖 3D 視差傾斜 |
| 左鍵拖曳（3D 場景）| 旋轉視角 |
| 右鍵拖曳　或　Shift+左鍵拖曳（3D 場景）| **平移整個畫面** |
| 滾輪（3D 場景）| 縮放 |
| ▶ 跑一次 Pipeline | 進度步驟器 + 逐步點亮 + 通訊日誌（跑一輪）|
| 🔁 循環 | 自動重複播放 Pipeline，持續看代理人溝通，不用一直手動啟動 |
| 🌙 / ☀️ | 切換深色 / 淺色（白底）主題，會記住你的選擇 |
| ⟳ 重置 | 3D 場景回總覽角度 / 架構圖捲回頂部 |

## 換成你自己的 3D 模型（glTF）

3D 場景**內建多個對味的真模型**（其餘節點用程序化模型）：
- **三代理人**（採集者 / 分析師 / 預警員）→ `drone.glb` 無人機（AI agent 風格，青/紫/綠光區分）
- **環境部 EPA** → `tower.glb` 監測塔　**Open-Meteo** → `satellite.glb` 氣象衛星　**民間感測器** → `antenna.glb` 感測天線
- **OpenClaw** → `lobster.glb` 龍蝦（專案吉祥物）

你也可以把任一節點換成自己的 **`.glb` / `.gltf`** 模型：

1. 把模型檔放進 `flowchart-site/models/`
2. 打開 `js/data.js`，在 `MODELS` 裡用「節點 id」對應檔案：
   ```js
   const MODELS = {
     openclaw: { url: "models/你的模型.glb", scale: 1.0, rot: [0, 0, 0], yOff: 0, spin: 0.4 },
     collector: { url: "models/lobster.glb", scale: 1.5 },
   };
   ```
   - `scale` 縮放、`rot` [x,y,z] 弧度、`yOff` 高度微調、`spin` 自轉速度
   - 找不到檔或載入失敗 → 自動退回程序化模型（不會壞）
3. **用 `start.bat` 開**（`file://` 直接開會被瀏覽器擋住載入二進位模型）

> 預設沒有對應任何模型，所有節點都是程序化模型。對應後找不到檔 / 載入失敗都會自動退回程序化版。
> 模型哪裡來：AI 生成（Meshy / Tripo / Luma）、免費庫（Sketchfab / Poly Pizza / Quaternius）、或 Blender / Spline 匯出。建議低多邊形（< 5–10 萬面）。

節點 id：`user / app / collector / analyst / advisor / epa / openmeteo / civic / rag / llm / sqlite / discord / openclaw`

### 內建模型來源 / 授權
全部取自 [Poly Pizza](https://poly.pizza)，**CC-BY** 授權（各模型作者見其頁面，再散布時請保留標示）：
- `lobster.glb` — *Lobster* by **Poly by Google**（[來源](https://poly.pizza/m/7JIU-w5So3a)）
- `drone.glb` — *Drone with Orb*、`satellite.glb` — *Satellite*、`tower.glb` — *Radio tower*、`antenna.glb` — *Antenna*（皆來自 Poly Pizza，CC-BY）

> 區域工作流標籤（用戶層 / 外部資料源 / 三代理人 Pipeline / 外部服務整合 / 資料儲存層）已標在 3D 場景中；右上「🔁 循環」可讓 Pipeline 自動重播，不用一直手動啟動。

## 檔案結構

```
flowchart-site/
├── index.html        # 結構 + 視圖切換 + 進度步驟器
├── css/
│   ├── style.css     # 深色科技風主題 + 3D 場景 UI（配色取自專案 styles.py）
│   └── diagram.css   # 分層架構圖樣式（卡片 / 連線 / 3D 視差）
├── js/
│   ├── data.js       # 專案模型：節點/連線/城市/AQI/文獻/公式 + DIAGRAM + MODELS(glTF 設定)
│   ├── diagram.js    # 分層架構圖：建 DOM、SVG 資料流動畫、3D 視差、pipeline 進度
│   ├── scene.js      # 3D 場景：程序化模型 / glTF 載入、bloom 發光、資料封包通訊
│   ├── demos.js      # 各卡片/節點點開後的實際流程 demo（含 RAG 向量檢索）
│   └── main.js       # 接線：雙視圖切換 / 面板 / 統一 Pipeline 進度 + 封包動畫
├── models/           # ★ 放你自己的 .glb / .gltf 模型（預設空，用程序化模型）
└── vendor/           # Three.js r128 + bloom 後製 + GLTFLoader（本地，離線可用）
    ├── three.min.js
    ├── GLTFLoader.js
    └── EffectComposer.js / UnrealBloomPass.js / …（霓虹發光）
```

> 除錯開關（網址列 console 設定後重整）：`window.LOBSTER_NOBLOOM=true` 關閉 bloom。

字型（Inter / JetBrains Mono / Noto Sans TC）走 Google Fonts；無網路時自動退回系統字型，3D 標籤用系統 CJK 字型繪製，不受影響。
