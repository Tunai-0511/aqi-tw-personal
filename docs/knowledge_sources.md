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
