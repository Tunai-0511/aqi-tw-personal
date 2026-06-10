import { C, base, title, card } from "./helpers.mjs";

export async function slide02(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "MOTIVATION");
  title(slide, ctx, "動機：AQI 不是同一個數字，對每個人卻是不同風險", "一般空品 App 告訴你現在空氣如何；AgentAQI 想回答「我該不該出門、該怎麼防護」。");
  card(slide, ctx, 70, 208, 330, 250, "痛點 1｜公開資料分散", "EPA 即時 AQI、24h 歷史、CAMS、Open-Meteo、民間感測器各有格式與延遲。使用者難以判斷哪個數字可信、何時更新。", C.cyan);
  card(slide, ctx, 475, 208, 330, 250, "痛點 2｜健康差異被忽略", "同樣 AQI 95，健康成人、過敏族群、COPD 長者的行動建議不同。傳統儀表板很少把年齡、疾病、個人閾值納入判斷。", C.orange);
  card(slide, ctx, 880, 208, 330, 250, "痛點 3｜通知缺乏上下文", "聊天 bot 若只回傳 AQI，仍需要使用者自己解讀。專案把資料整理成 JSON，讓 agent bot 能讀取同一份上下文。", C.green);
  ctx.addText(slide, { x: 120, y: 535, w: 1040, h: 56, text: "設計目標：用 multi-agent pipeline 把資料採集、風險分析、個人化建議拆開，讓結果既可視覺化，也能被 bot 轉述。", fontSize: 24, bold: true, color: C.ink, align: "center" });
  return slide;
}
