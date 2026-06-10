import { C, base, title, flowNode, arrow } from "./helpers.mjs";

export async function slide09(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "DEMO FLOW");
  title(slide, ctx, "Demo 操作路線：5 分鐘展示專案完整閉環", "從填個人資料到 bot 可讀 JSON，展示資料產品與 agent 整合不是兩套系統。");
  flowNode(slide, ctx, 72, 245, 185, 150, "1. 啟動 App", "run.bat\n開啟 localhost:8501\n載入 Streamlit", C.cyan);
  arrow(slide, ctx, 267, 310, 58, C.cyan);
  flowNode(slide, ctx, 337, 245, 185, 150, "2. 填健康檔案", "城市\n年齡 / BMI\nICD-10 / AQI 閾值", C.orange);
  arrow(slide, ctx, 532, 310, 58, C.orange);
  flowNode(slide, ctx, 602, 245, 185, 150, "3. 跑 Pipeline", "Collector\nAnalyst\nAdvisor\n約 10-30 秒", C.green);
  arrow(slide, ctx, 797, 310, 58, C.green);
  flowNode(slide, ctx, 867, 245, 185, 150, "4. 看 Section", "AQI 排名\n個人化推薦\n健康日誌", C.purple);
  arrow(slide, ctx, 1062, 310, 58, C.purple);
  flowNode(slide, ctx, 1130, 245, 100, 150, "5. Bot", "讀 JSON\n回覆提醒", C.red);
  ctx.addShape(slide, { x: 170, y: 480, w: 940, h: 90, fill: C.panel, line: ctx.line("#d6e2ee", 1) });
  ctx.addText(slide, { x: 205, y: 500, w: 870, h: 56, text: "備援展示：可先執行 scripts/seed_demo_data.py 產生 demo AQI 與健康日誌，避免現場網路或 API token 影響 demo。", fontSize: 20, color: C.ink, align: "center" });
  return slide;
}
