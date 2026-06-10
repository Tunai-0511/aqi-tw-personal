import { C, base, title, card } from "./helpers.mjs";

export async function slide04(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "SOLUTION");
  title(slide, ctx, "解法概覽：三個 agent 各司其職", "讓資料處理、風險判讀、健康建議保持清楚邊界，降低 LLM 幻覺與維護成本。");
  card(slide, ctx, 85, 205, 320, 275, "A｜採集者 Collector", "負責 ETL：抓 EPA 即時/歷史、Open-Meteo 氣象、CAMS 空品、Civil IoT / LASS PM2.5，並做清洗、欄位解析、fallback。", C.cyan);
  card(slide, ctx, 480, 205, 320, 275, "B｜分析員 Analyst", "把 AQI 趨勢、污染物組成、環境因子與 RAG 參考資料轉成摘要。LLM 負責解釋，不碰原始資料可信度。", C.orange);
  card(slide, ctx, 875, 205, 320, 275, "C｜預警員 Advisor", "讀取個人健康檔案與 AQI 閾值，生成針對城市、疾病、年齡與外出情境的防護建議。", C.green);
  ctx.addShape(slide, { x: 130, y: 548, w: 1020, h: 72, fill: "#eef6fb", line: ctx.line(C.cyan, 1) });
  ctx.addText(slide, { x: 160, y: 568, w: 960, h: 36, text: "輸出：Streamlit 10 個 section + SQLite 時序快取 + hermes_export/latest_aqi.json", fontSize: 24, bold: true, color: C.ink, align: "center" });
  return slide;
}
