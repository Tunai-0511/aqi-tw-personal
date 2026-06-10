# TOOLS.md — What I Can Use

## aqi-live(本專案 skill)

讀 `hermes_export/latest_aqi.json`(AgentAQI Pipeline 每次跑完更新)。

- 提供:全台 20 城市快照、全國概況、分析師摘要、各城市建議、使用者 persona。
- 契約與觸發規則見 `hermes_skills/aqi-live/SKILL.md`。
- 本機 CLI 預覽(就是我會貼進 Discord 的內容):
  ```
  python hermes_skills/aqi-live/read_export.py [城市名]
  ```
- 匯出檔路徑可用環境變數 `AGENTAQI_EXPORT` 覆寫(預設專案根的 `hermes_export/`)。

不需要任何外部 API key —— 資料是 AgentAQI 預先抓好、匯出的。
我只負責「讀 JSON + 在 Discord 回答」,不自己呼叫 EPA / Open-Meteo / LLM。
