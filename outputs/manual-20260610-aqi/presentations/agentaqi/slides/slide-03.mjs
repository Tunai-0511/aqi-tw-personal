import { C, base, title, bulletList, metric } from "./helpers.mjs";

export async function slide03(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "PRODUCT IDEA");
  title(slide, ctx, "核心想法：從空品儀表板變成個人健康決策助理", "專案不是只做圖表，而是把資料、使用者狀態與可行動建議接在一起。");
  ctx.addShape(slide, { x: 70, y: 205, w: 500, h: 360, fill: C.panel, line: ctx.line("#d6e2ee", 1) });
  ctx.addText(slide, { x: 105, y: 235, w: 430, h: 42, text: "一般 AQI Dashboard", fontSize: 28, bold: true, color: C.muted });
  bulletList(slide, ctx, 110, 306, 390, ["顯示目前 AQI 與污染物", "資料來源與延遲常不透明", "建議通常只有固定文字", "無法被聊天平台直接重用"], C.muted);
  ctx.addShape(slide, { x: 650, y: 205, w: 500, h: 360, fill: "#eef6fb", line: ctx.line(C.cyan, 2) });
  ctx.addText(slide, { x: 685, y: 235, w: 430, h: 42, text: "AgentAQI", fontSize: 28, bold: true, color: C.cyan });
  bulletList(slide, ctx, 690, 306, 390, ["彙整官方、模式、民間感測器", "加入個人城市、年齡、疾病、AQI 閾值", "LLM/RAG 產生可行動建議", "匯出 latest_aqi.json 給 Agent Bot"], C.cyan);
  metric(slide, ctx, 92, 604, 250, "互動介面", "Streamlit", C.cyan);
  metric(slide, ctx, 380, 604, 250, "資料快取", "SQLite", C.green);
  metric(slide, ctx, 662, 604, 250, "圖表引擎", "Plotly", C.orange);
  metric(slide, ctx, 945, 604, 250, "Bot 介面", "Hermes", C.purple);
  return slide;
}
