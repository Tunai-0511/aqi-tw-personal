export const C = {
  bg: "#ffffff",
  panel: "#f4f8fb",
  panel2: "#eef6fb",
  ink: "#102033",
  sub: "#40546d",
  muted: "#708196",
  cyan: "#008fc4",
  orange: "#e46f24",
  green: "#00a85a",
  yellow: "#ffd93d",
  red: "#d9384a",
  purple: "#7a42d6",
  white: "#ffffff",
};

export function base(slide, ctx, kicker = "") {
  ctx.addShape(slide, { x: 0, y: 0, w: ctx.W, h: ctx.H, fill: C.bg });
  ctx.addShape(slide, { x: 0, y: 0, w: 16, h: ctx.H, fill: C.cyan });
  ctx.addShape(slide, { x: 16, y: 0, w: 5, h: ctx.H, fill: C.orange });
  if (kicker) {
    ctx.addText(slide, { x: 62, y: 32, w: 500, h: 28, text: kicker, fontSize: 14, bold: true, color: C.cyan });
  }
  ctx.addText(slide, { x: 1100, y: 704, w: 118, h: 12, text: "AgentAQI", fontSize: 8, color: C.muted, align: "right" });
}

export function title(slide, ctx, text, sub = "") {
  ctx.addText(slide, { x: 60, y: 68, w: 950, h: 86, text, fontSize: 35, bold: true, color: C.ink, typeface: ctx.fonts.title });
  if (sub) ctx.addText(slide, { x: 62, y: 154, w: 980, h: 34, text: sub, fontSize: 16, color: C.sub });
}

export function card(slide, ctx, x, y, w, h, head, body, color = C.cyan) {
  ctx.addShape(slide, { x, y, w, h, fill: C.panel, line: ctx.line("#d6e2ee", 1) });
  ctx.addShape(slide, { x, y, w: 7, h, fill: color });
  ctx.addText(slide, { x: x + 22, y: y + 18, w: w - 38, h: 28, text: head, fontSize: 20, bold: true, color: C.ink });
  ctx.addText(slide, { x: x + 22, y: y + 56, w: w - 38, h: h - 72, text: body, fontSize: 15, color: C.sub, insets: { left: 0, right: 0, top: 0, bottom: 0 } });
}

export function metric(slide, ctx, x, y, w, label, value, color = C.cyan) {
  ctx.addText(slide, { x, y, w, h: 46, text: value, fontSize: 32, bold: true, color });
  ctx.addText(slide, { x, y: y + 54, w, h: 34, text: label, fontSize: 13, color: C.sub });
}

export function pill(slide, ctx, x, y, w, text, color = C.cyan) {
  ctx.addShape(slide, { x, y, w, h: 34, fill: "#f6fbff", line: ctx.line(color, 1) });
  ctx.addText(slide, { x: x + 12, y: y + 7, w: w - 24, h: 22, text, fontSize: 13, bold: true, color });
}

export function flowNode(slide, ctx, x, y, w, h, head, body, color = C.cyan) {
  ctx.addShape(slide, { x, y, w, h, fill: "#ffffff", line: ctx.line(color, 2) });
  ctx.addShape(slide, { x, y, w, h: 10, fill: color });
  ctx.addText(slide, { x: x + 15, y: y + 22, w: w - 30, h: 26, text: head, fontSize: 17, bold: true, color: "#07111f" });
  ctx.addText(slide, { x: x + 15, y: y + 54, w: w - 30, h: h - 72, text: body, fontSize: 12, color: "#24364f" });
}

export function arrow(slide, ctx, x, y, w, color = C.cyan, label = "") {
  ctx.addShape(slide, { x, y: y + 10, w, h: 3, fill: color });
  ctx.addText(slide, { x: x + w - 24, y: y - 2, w: 24, h: 28, text: ">", fontSize: 22, bold: true, color });
  if (label) ctx.addText(slide, { x, y: y - 21, w: w + 24, h: 18, text: label, fontSize: 11, color: C.sub, align: "center" });
}

export function bulletList(slide, ctx, x, y, w, items, color = C.cyan) {
  items.forEach((item, i) => {
    const yy = y + i * 56;
    ctx.addShape(slide, { x, y: yy + 8, w: 10, h: 10, fill: color });
    ctx.addText(slide, { x: x + 24, y: yy, w, h: 44, text: item, fontSize: 17, color: C.sub });
  });
}
