import { C, base, title, card, bulletList } from "./helpers.mjs";

export async function slide07(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "IMPLEMENTATION");
  title(slide, ctx, "怎麼做到：用 Streamlit 把資料產品、agent pipeline 與 bot 介面串起來", "核心檔案分工清楚，方便 demo、測試與後續擴充。");
  ctx.addShape(slide, { x: 70, y: 190, w: 520, h: 420, fill: C.panel, line: ctx.line("#d6e2ee", 1) });
  ctx.addText(slide, { x: 105, y: 220, w: 430, h: 34, text: "程式分工", fontSize: 26, bold: true, color: C.ink });
  bulletList(slide, ctx, 110, 288, 420, [
    "app.py：Streamlit 主介面、10 個 section、pipeline orchestration",
    "data.py：資料抓取、清洗、LLM provider、Hermes payload",
    "charts.py：Plotly 圖表與視覺元件",
    "tsdb.py：SQLite 時序快取、健康日誌",
    "scripts/record_feel.py：Discord feel 1~5 打卡匯入"
  ], C.cyan);
  card(slide, ctx, 660, 190, 250, 180, "UI 層", "城市 AQI 排名、24h 趨勢、熱力圖、污染物雷達、環境關聯、官方 vs 民間感測器。", C.cyan);
  card(slide, ctx, 940, 190, 250, 180, "個人化層", "讀取使用者城市、年齡、BMI、疾病代碼、AQI 閾值，生成安全外出與防護建議。", C.orange);
  card(slide, ctx, 660, 410, 250, 180, "記錄層", "SQLite 保存 CAMS hourly、AQI snapshots、health_diary，形成 7 天趨勢與症狀相關分析。", C.green);
  card(slide, ctx, 940, 410, 250, 180, "Agent Bot 層", "pipeline 跑完寫出 latest_aqi.json；Hermes skill 讀取 JSON 後在 Discord 回覆。", C.purple);
  return slide;
}
