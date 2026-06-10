import { C, base, title, card, metric } from "./helpers.mjs";

export async function slide10(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "VALUE");
  title(slide, ctx, "價值與下一步：把空品監測變成可延伸的個人健康 agent", "目前已完成 dashboard、pipeline、JSON 匯出與健康日誌；後續可往主動通知與更完整個人模型前進。");
  metric(slide, ctx, 86, 190, 250, "資料整合", "API + SQLite", C.cyan);
  metric(slide, ctx, 380, 190, 250, "決策支援", "LLM / RAG", C.orange);
  metric(slide, ctx, 680, 190, 250, "個人化", "Profile + Threshold", C.green);
  metric(slide, ctx, 980, 190, 220, "Bot 擴充", "JSON Contract", C.purple);
  card(slide, ctx, 90, 330, 310, 215, "已做到", "10-section Streamlit App、即時/歷史空品、民間感測器比較、個人化健康卡、症狀 vs AQI 分析、Hermes JSON 匯出。", C.green);
  card(slide, ctx, 485, 330, 310, 215, "可改進", "加入排程與 webhook，讓 bot 主動提醒；擴充 embedding RAG；把使用者長期日誌變成更穩定的個人敏感度模型。", C.orange);
  card(slide, ctx, 880, 330, 310, 215, "專案亮點", "不是單純 dashboard，而是可視化 App + agent pipeline + bot contract 的完整小型健康資料產品。", C.cyan);
  ctx.addText(slide, { x: 165, y: 604, w: 950, h: 56, text: "結論：AgentAQI 讓空氣品質資料從「被看見」走到「能被理解、能被行動、能被 agent 轉述」。", fontSize: 24, bold: true, color: C.ink, align: "center" });
  return slide;
}
