# SKILL.md — AQI Live（讀 AgentAQI 匯出）

## Purpose

讓聊天平台的 Agent Bot(本機範例:Hermes/Discord;LINE / Slack / Telegram 皆可)回答台灣空品問題,資料來自 AgentAQI Pipeline 匯出的
`agent_export/latest_aqi.json`。這是**拉取(pull)模型** —— 不是 AgentAQI 推給
Hermes,而是 Hermes「來這裡讀」最新一次 Pipeline 的結果。

## 資料來源

`<AgentAQI 專案根>/agent_export/latest_aqi.json`,每次使用者在 AgentAQI 跑一次
Pipeline 就更新(UTF-8 JSON)。路徑可用環境變數 `AGENTAQI_EXPORT` 覆寫。

## JSON 契約（由 `data.build_agent_payload()` 產生）

| 欄位 | 說明 |
|------|------|
| `generated_at` | 匯出時間(ISO) |
| `data_mode` | `real` / `mock` / `demo` —— 回答時要誠實標示 |
| `national` | `{avg_aqi, worst:{city,aqi,level}, best:{city,aqi,level}}` |
| `cities[]` | 20 城市 `{city_id, city, region, aqi, level, pm25, pm10, o3, no2, so2, co, risk}` |
| `analyst_summary` | 分析師風險摘要(純文字) |
| `advisories` | `{城市名: 預警員建議文字}`(目前為「所選城市」一筆的詳細分節建議) |
| `user_profile` | `{age, sex, bmi, bmi_category, diagnoses[], med_history, city, threshold}` 或 `null` |
| `user_city` / `user_city_name` / `user_city_advice` | 使用者常駐城市與其建議 |
| `threshold` | 個人 AQI 預警閾值(同 `user_profile.threshold`,頂層重複一份方便取用) |

## 聊天平台觸發 → 回答規則(平台不限,以 Discord 為例)

- `@bot` / 訊息含「空氣」「空品」「AQI」→ 回全國概況(`national`)。
- 訊息含城市名(如「台北」)→ 回該城市 AQI + 等級 + `advisories[該城市]`。
- `user_profile` 非 null → 加一句個人化提醒(依 `age` / `diagnoses` / `bmi`);
  查詢城市的 AQI 若超過 `threshold`(使用者自設閾值)→ 額外標「⚠ 已超過你設定的個人預警閾值」。
- `data_mode != real` → 開頭標「(模擬 / demo 資料)」。
- 找不到城市 / 檔案不存在 / 過舊 → 明說,不要猜。

## 本機驗證（不用任何聊天平台）

```
python agent_skills/aqi-live/read_export.py            # 全國概況
python agent_skills/aqi-live/read_export.py 台北市      # 指定城市 + persona 提醒
```

印出的文字就是 bot 會貼進聊天平台的內容。bot 端可直接呼叫這支腳本,
或在 Hermes 內以等價邏輯讀同一份 JSON。
