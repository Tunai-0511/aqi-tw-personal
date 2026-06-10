import { C, base, title, flowNode, arrow } from "./helpers.mjs";

export async function slide05(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "FLOWCHART");
  title(slide, ctx, "流程圖：從外部資料到個人化建議與 bot 回覆", "主線是 pipeline；支線是本機快取與 JSON 匯出，讓 App 與 Agent Bot 讀同一份結果。");
  flowNode(slide, ctx, 60, 240, 180, 150, "資料來源", "EPA AQI\nEPA 24h\nCAMS / Open-Meteo\nCivil IoT / LASS", C.cyan);
  arrow(slide, ctx, 250, 305, 58, C.cyan, "HTTP");
  flowNode(slide, ctx, 320, 220, 190, 190, "Collector", "欄位解析\n資料清洗\n城市平均\nreal / mock / demo 標示", C.cyan);
  arrow(slide, ctx, 520, 305, 58, C.orange, "DataFrame");
  flowNode(slide, ctx, 590, 220, 190, 190, "Analyst", "趨勢摘要\n污染物剖析\n環境關聯\nRAG 重點", C.orange);
  arrow(slide, ctx, 790, 305, 58, C.green, "profile");
  flowNode(slide, ctx, 860, 220, 190, 190, "Advisor", "年齡 / BMI\nICD-10 / 閾值\n防護建議\nsafe_hours", C.green);
  arrow(slide, ctx, 1060, 305, 58, C.purple, "export");
  flowNode(slide, ctx, 1128, 220, 110, 190, "輸出", "Dashboard\nJSON\nBot", C.purple);
  ctx.addShape(slide, { x: 330, y: 470, w: 190, h: 74, fill: C.panel2, line: ctx.line(C.green, 1) });
  ctx.addText(slide, { x: 350, y: 490, w: 150, h: 32, text: "SQLite\n時序快取 / health diary", fontSize: 15, bold: true, color: C.ink, align: "center" });
  ctx.addShape(slide, { x: 920, y: 470, w: 230, h: 74, fill: C.panel2, line: ctx.line(C.purple, 1) });
  ctx.addText(slide, { x: 940, y: 491, w: 190, h: 32, text: "hermes_export/latest_aqi.json\n給 Discord / LINE bot 讀取", fontSize: 14, bold: true, color: C.ink, align: "center" });
  ctx.addShape(slide, { x: 412, y: 410, w: 3, h: 52, fill: C.green });
  ctx.addShape(slide, { x: 1032, y: 410, w: 3, h: 52, fill: C.purple });
  ctx.addText(slide, { x: 78, y: 600, w: 1070, h: 40, text: "關鍵設計：資料抓取與個人化文字生成分層，LLM 只負責解釋與建議；數值、分級、快取由 Python 控制。", fontSize: 21, color: C.sub, align: "center" });
  return slide;
}
