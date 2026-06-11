from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

OUT = Path(__file__).resolve().parent
W, H = 1920, 1080
FONT = r"C:\Windows\Fonts\NotoSansTC-VF.ttf"
FONT_B = r"C:\Windows\Fonts\msjhbd.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


C = {
    "ink": (26, 34, 46),
    "muted": (92, 105, 122),
    "line": (218, 226, 236),
    "blue": (28, 112, 235),
    "blue2": (231, 241, 255),
    "green": (14, 150, 106),
    "green2": (226, 247, 239),
    "orange": (238, 133, 45),
    "orange2": (255, 243, 228),
    "red": (222, 75, 75),
    "red2": (255, 235, 235),
    "purple": (116, 85, 205),
    "purple2": (241, 237, 255),
    "bg": (255, 255, 255),
    "soft": (248, 250, 253),
}


slides = [
    ("01", "封面", "AgentAQI 監控平台", "台灣空氣品質 × 個人健康 × 3-Agent 分析",
     ["一句話：把即時 AQI 轉成看得懂、用得上的健康建議", "4 人團隊 · 30 秒開場"], "cover"),
    ("02", "動機 / 痛點", "誰很痛，痛在哪？", "空品資訊很多，但真正難的是即時判讀與個人化決策",
     ["高敏感族群不知道何時該減少外出", "資料分散：官方測站、民間感測器、天氣與歷史趨勢", "一般 AQI 數字不等於個人化行動建議"], "pain"),
    ("03", "解決方案定位", "我們做了一個個人化空品 Agent 平台", "解決：資料整合、風險判讀、健康建議、聊天平台查詢",
     ["即時 AQI + 24h / 7d 趨勢", "RAG + LLM 產生風險分析", "依年齡、BMI、診斷與城市做個人化建議"], "position"),
    ("04", "使用情境", "誰在什麼時候怎麼用？", "從打開儀表板到聊天平台查詢，一條線完成",
     ["使用者設定個人健康資料與城市", "Pipeline 更新即時空品與健康提醒", "Agent Bot 可在 Discord / LINE / Slack 查詢"], "scenario"),
    ("05", "系統架構圖", "資料怎麼流、模組怎麼接", "核心：Streamlit → 3-Agent Pipeline → SQLite / JSON / Dashboard",
     ["資料來源：EPA、Open-Meteo、CAMS、CivilIoT、LASS", "處理：data.py、run_pipeline()、tsdb.py", "輸出：SECTION 01-10、agent_export/latest_aqi.json"], "architecture"),
    ("06", "如何做到", "技術選型與關鍵做法", "用簡單可靠的堆疊，把資料、分析、展示與 Bot 串起來",
     ["Streamlit：快速做互動式 dashboard", "pandas / requests：ETL 與 API 整理", "Plotly：地圖、趨勢、熱力圖、雷達圖", "SQLite：本機時序資料與健康日誌", "LLM API + RAG：分析與個人化建議"], "tech"),
    ("07", "數據", "撐住論點的證據", "用資料源與圖表說明，不只用口頭描述",
     ["官方資料：EPA 即時 AQI / 歷史 AQI", "模型資料：Open-Meteo CAMS 24h / 7d", "民間資料：CivilIoT / LASS PM2.5", "圖表：排名、地圖、趨勢、熱力圖、相關性"], "data"),
    ("08", "Demo", "高潮信息：給足時間，最好備援", "現場展示從啟動 Pipeline 到 Agent Bot 查詢",
     ["填個人資料與城市", "啟動 3-Agent Pipeline", "看即時 AQI、健康預警、健康日誌", "預覽 agent_export/latest_aqi.json 與 Bot 回覆"], "demo"),
    ("09", "成果", "量化結果 + 達成了什麼", "把成果講成可驗證的輸出，而不是只說功能很多",
     ["整合 20 縣市即時 AQI 與多來源資料", "建立 24h / 7d 趨勢與 SQLite 快取", "產生個人化健康建議與 Agent Bot JSON", "完成 SECTION 01-10 可展示流程"], "result"),
    ("10", "分工表", "快速帶過，誰負責哪塊", "30 秒讓評審知道專案不是一個人硬拚",
     ["成員 A：資料來源、ETL、API 串接", "成員 B：Streamlit UI、圖表與互動", "成員 C：LLM / RAG / Agent Prompt", "成員 D：Demo、測試、文件與整合"], "team"),
    ("11", "結語 / 未來展望", "收尾、謝謝、進 Q&A", "AgentAQI 把空品資料變成個人可行動的健康提醒",
     ["未來：推播提醒、更多穿戴資料、部署雲端", "擴充：更多城市、更多感測器、更多聊天平台", "謝謝大家，歡迎提問"], "closing"),
]


def rr(d, xy, r=24, fill=(255, 255, 255), outline=None, width=2):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def text(d, xy, s, size=40, fill=None, bold=False, anchor=None):
    d.text(xy, s, font=font(size, bold), fill=fill or C["ink"], anchor=anchor)


def wrap(d, s, size, maxw):
    f = font(size)
    lines, cur = [], ""
    for ch in s:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if d.textlength(trial, font=f) <= maxw:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def multiline(d, xy, s, size=34, fill=None, maxw=700, line_gap=12, bold=False):
    y = xy[1]
    for line in wrap(d, s, size, maxw):
        d.text((xy[0], y), line, font=font(size, bold), fill=fill or C["ink"])
        y += size + line_gap
    return y


def header(d, no, section):
    rr(d, (72, 52, 176, 112), 30, C["ink"])
    text(d, (124, 81), no, 30, (255, 255, 255), True, "mm")
    text(d, (205, 65), section, 30, C["muted"], True)
    d.line((72, 136, 1848, 136), fill=C["line"], width=2)


def pill(d, xy, label, color, fill, size=28):
    x, y = xy
    f = font(size, True)
    w = d.textlength(label, font=f) + 44
    rr(d, (x, y, x + w, y + 54), 27, fill)
    d.ellipse((x + 18, y + 19, x + 28, y + 29), fill=color)
    d.text((x + 38, y + 11), label, font=f, fill=color)
    return x + w + 16


def arrow(d, p1, p2, color=None, width=5):
    color = color or C["blue"]
    d.line((p1, p2), fill=color, width=width)
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    l = 18
    a1 = ang + math.pi * .82
    a2 = ang - math.pi * .82
    d.polygon([p2, (p2[0] + l * math.cos(a1), p2[1] + l * math.sin(a1)),
               (p2[0] + l * math.cos(a2), p2[1] + l * math.sin(a2))], fill=color)


def card(d, xy, title, body, accent=C["blue"], fill=C["soft"]):
    x1, y1, x2, y2 = xy
    rr(d, xy, 26, fill, C["line"], 2)
    d.rectangle((x1, y1, x1 + 8, y2), fill=accent)
    text(d, (x1 + 34, y1 + 26), title, 34, C["ink"], True)
    multiline(d, (x1 + 34, y1 + 78), body, 26, C["muted"], x2 - x1 - 68, 8)


def draw_flow(d):
    xs = [160, 500, 850, 1200, 1570]
    labels = [("UI", "Streamlit\n個人資料"), ("A", "資料收集\n清理"), ("B", "RAG +\n分析"),
              ("C", "健康\n建議"), ("輸出", "Dashboard\nSQLite / JSON")]
    for i, (t, b) in enumerate(labels):
        rr(d, (xs[i] - 95, 760, xs[i] + 95, 900), 24, C["blue2"] if i < 4 else C["green2"], C["line"], 2)
        text(d, (xs[i], 795), t, 34, C["blue"] if i < 4 else C["green"], True, "mm")
        for j, line in enumerate(b.split("\n")):
            text(d, (xs[i], 835 + j * 30), line, 24, C["ink"], False, "mm")
        if i < 4:
            arrow(d, (xs[i] + 105, 830), (xs[i + 1] - 105, 830), C["blue"], 4)


def base(no, section, title, subtitle):
    im = Image.new("RGB", (W, H), C["bg"])
    d = ImageDraw.Draw(im)
    header(d, no, section)
    text(d, (90, 190), title, 64, C["ink"], True)
    multiline(d, (94, 282), subtitle, 32, C["muted"], 1400, 10)
    return im, d


for no, sec, title, sub, bullets, kind in slides:
    im, d = base(no, sec, title, sub)
    if kind == "cover":
        draw_flow(d)
        x = 94
        for name, col, fill in [("即時 AQI", C["blue"], C["blue2"]), ("個人化健康", C["green"], C["green2"]),
                                ("3-Agent Pipeline", C["purple"], C["purple2"]), ("Agent Bot 拉取", C["orange"], C["orange2"])]:
            x = pill(d, (x, 395), name, col, fill, 30)
        card(d, (94, 505, 790, 690), "一句話標語", bullets[0], C["blue"], C["soft"])
        card(d, (840, 505, 1460, 690), "開場提醒", bullets[1], C["green"], C["soft"])
        for i in range(4):
            cx, cy = 1570 + i * 70, 590
            d.ellipse((cx - 26, cy - 26, cx + 26, cy + 26), fill=[C["blue"], C["green"], C["orange"], C["purple"]][i])
            text(d, (cx, cy + 3), chr(ord("A") + i), 26, (255, 255, 255), True, "mm")
    elif kind == "pain":
        labels = [("資訊太分散", "官方、民間、天氣、歷史趨勢分開看"), ("個人差異大", "年齡、BMI、疾病會改變風險"),
                  ("數字難行動", "AQI 變高時，不知道該怎麼做")]
        for i, (a, b) in enumerate(labels):
            card(d, (94 + i * 590, 440, 610 + i * 590, 680), a, b,
                 [C["red"], C["orange"], C["purple"]][i], [C["red2"], C["orange2"], C["purple2"]][i])
        d.line((180, 820, 1680, 820), fill=C["line"], width=8)
        for x, l in [(330, "資料"), (800, "判讀"), (1270, "行動")]:
            d.ellipse((x - 38, 782, x + 38, 858), fill=C["red2"], outline=C["red"], width=3)
            text(d, (x, 820), l, 28, C["red"], True, "mm")
    elif kind == "position":
        card(d, (110, 430, 510, 650), "我們做了", bullets[0], C["blue"], C["blue2"])
        arrow(d, (530, 540), (690, 540), C["blue"], 5)
        card(d, (710, 430, 1110, 650), "用 Agent 分析", bullets[1], C["purple"], C["purple2"])
        arrow(d, (1130, 540), (1290, 540), C["blue"], 5)
        card(d, (1310, 430, 1710, 650), "給個人建議", bullets[2], C["green"], C["green2"])
        card(d, (330, 760, 1590, 900), "定位一句話", "不是只顯示 AQI，而是把空品資料轉成個人可行動的健康提醒。",
             C["orange"], C["orange2"])
    elif kind == "scenario":
        steps = [("1", "填資料", "城市、年齡、BMI、診斷"), ("2", "跑 Pipeline", "更新 AQI 與趨勢"),
                 ("3", "看 Dashboard", "風險、預警、日誌"), ("4", "問 Bot", "聊天平台讀 JSON 回答")]
        for i, (n, t, b) in enumerate(steps):
            x = 130 + i * 435
            rr(d, (x, 430, x + 330, 700), 28, C["soft"], C["line"], 2)
            d.ellipse((x + 28, 455, x + 88, 515), fill=C["blue"])
            text(d, (x + 58, 486), n, 28, (255, 255, 255), True, "mm")
            text(d, (x + 112, 462), t, 34, C["ink"], True)
            multiline(d, (x + 34, 548), b, 28, C["muted"], 260, 8)
            if i < 3:
                arrow(d, (x + 340, 565), (x + 410, 565), C["blue"], 4)
        card(d, (270, 800, 1650, 925), "使用情境重點", "同一份資料同時支援儀表板、健康日誌與聊天平台查詢。",
             C["green"], C["green2"])
    elif kind == "architecture":
        card(d, (80, 420, 360, 650), "Streamlit UI", "設定與啟動\napp.py", C["blue"], C["blue2"])
        arrow(d, (380, 535), (500, 535), C["blue"], 5)
        card(d, (520, 380, 850, 690), "3-Agent Pipeline", "A 採集者\nB 分析師\nC 預警員", C["purple"], C["purple2"])
        arrow(d, (870, 535), (980, 535), C["blue"], 5)
        card(d, (1000, 350, 1360, 720), "資料處理", "data.py\ntsdb.py\ncharts.py", C["orange"], C["orange2"])
        arrow(d, (1380, 535), (1490, 535), C["blue"], 5)
        card(d, (1510, 330, 1840, 745), "輸出", "Dashboard\nSQLite\nagent_export JSON\nAgent Bot", C["green"], C["green2"])
        x = 140
        for p in ["EPA", "Open-Meteo", "CAMS", "CivilIoT", "LASS"]:
            x = pill(d, (x, 805), p, C["blue"], C["soft"], 26)
    elif kind == "tech":
        techs = [("Streamlit", "互動式 Dashboard"), ("pandas / requests", "API ETL 與資料清理"), ("Plotly", "地圖、趨勢、熱力圖"),
                 ("SQLite", "時序快取與健康日誌"), ("LLM + RAG", "分析與個人化建議")]
        for i, (a, b) in enumerate(techs):
            row, col = i // 3, i % 3
            x, y = 110 + col * 585, 420 + row * 230
            card(d, (x, y, x + 490, y + 165), a, b, [C["blue"], C["green"], C["orange"], C["purple"], C["red"]][i], C["soft"])
        card(d, (400, 900, 1520, 990), "關鍵做法", "把複雜系統拆成可維護的資料層、Pipeline、視覺化與 Bot 匯出。",
             C["blue"], C["blue2"])
    elif kind == "data":
        for i, bh in enumerate([310, 480, 650, 820]):
            d.rectangle((250 + i * 150, 850 - bh // 2, 340 + i * 150, 850),
                        fill=[C["blue"], C["green"], C["orange"], C["purple"]][i])
            text(d, (295 + i * 150, 890), ["EPA", "CAMS", "IoT", "LASS"][i], 24, C["muted"], True, "mm")
        d.line((200, 850, 920, 850), fill=C["line"], width=3)
        d.line((200, 430, 200, 850), fill=C["line"], width=3)
        for i, b in enumerate(bullets):
            card(d, (1030, 390 + i * 130, 1800, 490 + i * 130), f"證據 {i + 1}", b,
                 C["blue"] if i < 2 else C["green"], C["soft"])
    elif kind == "demo":
        for i, b in enumerate(bullets):
            y = 410 + i * 120
            d.ellipse((130, y + 5, 190, y + 65), fill=C["blue"])
            text(d, (160, y + 37), str(i + 1), 26, (255, 255, 255), True, "mm")
            card(d, (230, y, 1720, y + 86), "Demo Step", b, C["blue"] if i < 2 else C["green"], C["soft"])
        rr(d, (1320, 780, 1760, 930), 28, C["orange2"], C["orange"], 3)
        text(d, (1540, 820), "備援提醒", 34, C["orange"], True, "mm")
        multiline(d, (1370, 860), "準備錄影與假資料，現場 API 不穩也能展示。", 26, C["ink"], 340, 8)
    elif kind == "result":
        nums = [("20", "縣市即時 AQI"), ("24h / 7d", "趨勢與快取"), ("10", "Dashboard Sections"), ("1", "平台中性 JSON")]
        for i, (n, l) in enumerate(nums):
            x = 130 + i * 430
            rr(d, (x, 430, x + 330, 670), 30, C["green2"], C["green"], 3)
            text(d, (x + 165, 520), n, 62, C["green"], True, "mm")
            text(d, (x + 165, 592), l, 28, C["ink"], True, "mm")
        for i, b in enumerate(bullets):
            text(d, (260, 760 + i * 52), "✓", 32, C["green"], True)
            text(d, (315, 758 + i * 52), b, 30, C["ink"], False)
    elif kind == "team":
        y0 = 390
        cols = [90, 360, 910, 1430]
        heads = ["成員", "負責內容", "主要產出", "時間"]
        for x, h in zip(cols, heads):
            text(d, (x, y0), h, 30, C["muted"], True)
        d.line((80, y0 + 55, 1840, y0 + 55), fill=C["line"], width=3)
        rows = [("A", "資料來源、ETL、API 串接", "data.py / 外部資料", "30s"),
                ("B", "Streamlit UI、圖表與互動", "app.py / charts.py", "30s"),
                ("C", "LLM / RAG / Agent Prompt", "分析與健康建議", "30s"),
                ("D", "Demo、測試、文件與整合", "測試 / README / 展示", "30s")]
        for i, r in enumerate(rows):
            y = y0 + 90 + i * 110
            d.line((80, y + 75, 1840, y + 75), fill=C["line"], width=2)
            d.ellipse((100, y, 160, y + 60), fill=[C["blue"], C["green"], C["purple"], C["orange"]][i])
            text(d, (130, y + 32), r[0], 28, (255, 255, 255), True, "mm")
            text(d, (360, y + 12), r[1], 30, C["ink"])
            text(d, (910, y + 12), r[2], 30, C["ink"])
            text(d, (1430, y + 12), r[3], 30, C["muted"], True)
    elif kind == "closing":
        rr(d, (180, 410, 1740, 610), 34, C["blue2"], C["blue"], 3)
        multiline(d, (250, 465), bullets[0], 42, C["ink"], 1400, 10, True)
        card(d, (250, 705, 900, 880), "未來展望", bullets[1], C["green"], C["soft"])
        card(d, (990, 705, 1640, 880), "Q&A", bullets[2], C["purple"], C["soft"])
        text(d, (960, 960), "Thank You", 42, C["muted"], True, "mm")
    text(d, (90, 1012), "AgentAQI · presentation visual", 22, (150, 160, 174))
    im.save(OUT / f"page_{no}.png")


thumbs = []
for p in sorted(OUT.glob("page_*.png")):
    thumbs.append((p, Image.open(p).resize((384, 216))))
sheet = Image.new("RGB", (828, 80 + 216 * 6 + 10 * 5 + 40), (255, 255, 255))
ds = ImageDraw.Draw(sheet)
text(ds, (20, 20), "AgentAQI 簡報圖片預覽", 34, C["ink"], True)
for idx, (p, im) in enumerate(thumbs):
    x = 20 + (idx % 2) * 404
    y = 80 + (idx // 2) * 226
    sheet.paste(im, (x, y))
    ds.rectangle((x, y, x + 384, y + 216), outline=C["line"], width=2)
sheet.save(OUT / "contact_sheet.png")
