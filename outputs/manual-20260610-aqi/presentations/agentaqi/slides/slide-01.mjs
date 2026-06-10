import { C, base, metric, pill } from "./helpers.mjs";

export async function slide01(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx);
  ctx.addText(slide, { x: 72, y: 82, w: 650, h: 92, text: "AgentAQI", fontSize: 70, bold: true, color: C.ink, typeface: ctx.fonts.title });
  ctx.addText(slide, { x: 76, y: 174, w: 620, h: 70, text: "台灣空氣品質個人化 Multi-Agent 監測系統", fontSize: 28, color: C.cyan });
  ctx.addText(slide, { x: 78, y: 250, w: 640, h: 80, text: "把「今天 AQI 多少」升級成「我今天怎麼行動」：整合即時空品、個人健康檔案、LLM/RAG 建議與 bot 通知。", fontSize: 20, color: C.sub });
  pill(slide, ctx, 80, 365, 142, "Streamlit App", C.cyan);
  pill(slide, ctx, 238, 365, 142, "3-Agent Pipeline", C.orange);
  pill(slide, ctx, 396, 365, 146, "Hermes Bot JSON", C.green);
  ctx.addShape(slide, { x: 790, y: 102, w: 360, h: 360, fill: "#f4f8fb", line: ctx.line("#d6e2ee", 1) });
  ctx.addText(slide, { x: 846, y: 148, w: 250, h: 72, text: "AQI", fontSize: 56, bold: true, color: C.cyan, align: "center" });
  ctx.addText(slide, { x: 860, y: 229, w: 220, h: 42, text: "即時 · 預測 · 個人化", fontSize: 22, bold: true, color: C.ink, align: "center" });
  ctx.addShape(slide, { x: 870, y: 306, w: 200, h: 12, fill: C.green });
  ctx.addShape(slide, { x: 870, y: 325, w: 200, h: 12, fill: C.yellow });
  ctx.addShape(slide, { x: 870, y: 344, w: 200, h: 12, fill: C.orange });
  ctx.addShape(slide, { x: 870, y: 363, w: 200, h: 12, fill: C.red });
  metric(slide, ctx, 82, 512, 170, "台灣縣市監測", "20", C.cyan);
  metric(slide, ctx, 282, 512, 170, "核心 agent", "3", C.orange);
  metric(slide, ctx, 482, 512, 220, "主介面 section", "10", C.green);
  ctx.addText(slide, { x: 78, y: 638, w: 760, h: 28, text: "簡報重點：動機、流程圖、怎麼做到、使用情境", fontSize: 16, color: C.muted });
  return slide;
}
