import { C, base, title, card, pill } from "./helpers.mjs";

export async function slide06(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "DATA & MODEL");
  title(slide, ctx, "資料怎麼來：多來源、可降級、可追溯", "正式資料優先；API 失敗時仍能展示 mock/demo，但 UI 與 JSON 會標示資料模式。");
  card(slide, ctx, 70, 205, 265, 260, "官方測站", "環境部 Open Data：aqx_p_432 即時 AQI、aqx_p_488 24h 小時值。作為主畫面 AQI 的權威來源。", C.cyan);
  card(slide, ctx, 370, 205, 265, 260, "模式與氣象", "Open-Meteo 與 Copernicus CAMS 提供逐時空品與氣象，補足趨勢、預測與本週紀錄板。", C.orange);
  card(slide, ctx, 670, 205, 265, 260, "民間感測器", "Civil IoT / LASS 提供 PM2.5 高密度街區資料，用於官方 vs 民間比較，不硬轉成 AQI。", C.green);
  card(slide, ctx, 970, 205, 230, 260, "LLM/RAG", "支援 Anthropic、Gemini、MiniMax、OpenAI。RAG 用 WHO/EPA/研究資料輔助健康建議。", C.purple);
  pill(slide, ctx, 115, 535, 210, "real：真實 API 成功", C.green);
  pill(slide, ctx, 390, 535, 230, "mock：合理模型 fallback", C.yellow);
  pill(slide, ctx, 695, 535, 220, "demo：可重現展示資料", C.orange);
  pill(slide, ctx, 975, 535, 190, "SQLite：本機累積", C.cyan);
  ctx.addText(slide, { x: 115, y: 604, w: 1050, h: 40, text: "這個設計讓展示不依賴單一 API，也讓答辯時可以清楚說明：哪些是真實資料，哪些是 demo / fallback。", fontSize: 21, color: C.ink, align: "center" });
  return slide;
}
