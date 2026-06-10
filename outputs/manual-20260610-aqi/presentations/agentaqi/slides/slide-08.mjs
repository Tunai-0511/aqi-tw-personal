import { C, base, title, card } from "./helpers.mjs";

export async function slide08(presentation, ctx) {
  const slide = presentation.slides.add();
  base(slide, ctx, "SCENARIOS");
  title(slide, ctx, "使用情境：不同人看到同一份空品，得到不同決策", "AgentAQI 的價值在於把空品數據翻譯成個人可執行的建議。");
  card(slide, ctx, 70, 200, 340, 310, "情境 1｜COPD 長者", "72 歲、COPD、個人 AQI 閾值 50。當城市 AQI 逼近普通上緣，系統會比公定 AQI>100 更早提醒：減少外出、配戴 N95/KF94、避開尖峰時段。", C.red);
  card(slide, ctx, 470, 200, 340, 310, "情境 2｜過敏學生", "有過敏性鼻炎，準備通勤或運動。系統依城市趨勢、PM2.5 與氣象條件，給出是否延後戶外活動、是否戴口罩的建議。", C.orange);
  card(slide, ctx, 870, 200, 340, 310, "情境 3｜聊天平台查詢", "使用者在 Discord 問 bot 今天空品。bot 不重新打 API，而是讀 AgentAQI 匯出的 JSON，回覆全國平均、最高/最低城市與個人化提醒。", C.purple);
  ctx.addShape(slide, { x: 180, y: 570, w: 920, h: 54, fill: "#eef6fb", line: ctx.line(C.cyan, 1) });
  ctx.addText(slide, { x: 210, y: 586, w: 860, h: 26, text: "同一個 AQI 數字，最後落地成三種行動：看圖、做防護、讓 bot 主動轉述。", fontSize: 21, bold: true, color: C.ink, align: "center" });
  return slide;
}
