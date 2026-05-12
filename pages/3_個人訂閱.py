"""
Personal threshold subscription page.

Build an OpenClaw cron command from a form. User picks city + sensitive groups +
threshold + delivery channel → page generates the exact `openclaw cron add ...`
command line they can copy-paste, or run via subprocess after confirming.
"""
from __future__ import annotations

import shlex
import sys
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from data import CITIES, CITY_BY_ID, SENSITIVE_GROUPS
from styles import DARK_THEME_CSS, AGENT_STAGE_CSS


st.set_page_config(page_title="LobsterAQI · 個人訂閱", page_icon="🦞", layout="wide")
st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)
st.markdown(AGENT_STAGE_CSS, unsafe_allow_html=True)

if st.button("← 回主畫面"):
    st.switch_page("app.py")

st.markdown("<span class='eyebrow'>SUBSCRIBE · 個人推播訂閱</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>把預警送到你的 Discord / LINE</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>填好下面表單，會自動產生一條 OpenClaw cron 指令。"
    "可以複製貼到 terminal 跑，也可以直接按「立即註冊」讓本頁面幫你執行。</div>",
    unsafe_allow_html=True,
)


# ── Form ───────────────────────────────────────────────────────────────────
with st.form("subscription_form"):
    c1, c2 = st.columns(2)
    with c1:
        city = st.selectbox(
            "📍 你的城市",
            options=[c["id"] for c in CITIES],
            format_func=lambda cid: CITY_BY_ID[cid]["name"],
            index=next((i for i, c in enumerate(CITIES) if c["id"] == st.session_state.get("user_city", "taipei")), 0),
        )
        groups = st.multiselect(
            "🏥 你的敏感族群",
            options=[g["id"] for g in SENSITIVE_GROUPS],
            default=st.session_state.get("user_conditions", []),
            format_func=lambda gid: next(f"{g['icon']} {g['label']}" for g in SENSITIVE_GROUPS if g["id"] == gid),
        )
        threshold_aqi = st.slider("⚠ AQI 觸發閾值（超過時推送）", 50, 200, 100, step=10)
    with c2:
        channel = st.selectbox(
            "📡 推送頻道",
            options=["discord", "telegram", "slack", "matrix", "（不推送，只在主畫面看）"],
        )
        target = st.text_input(
            "頻道 ID / 對話 ID",
            placeholder="例如 channel:123456789012345678（Discord）或 telegram chat id",
            help="Discord: 從頻道右鍵 → 複製 ID（要先開啟開發者模式）",
        )
        cron_spec = st.selectbox(
            "推送頻率",
            options=[
                ("每小時整點", "0 * * * *"),
                ("每 30 分鐘", "*/30 * * * *"),
                ("每天早上 8 點", "0 8 * * *"),
                ("每天早上 8 點 + 晚上 6 點", "0 8,18 * * *"),
            ],
            format_func=lambda x: x[0],
        )

    submit = st.form_submit_button("產生指令", type="primary", use_container_width=True)


if submit:
    if channel == "（不推送，只在主畫面看）":
        st.info("✓ 已記住你的設定，回主畫面時可在「個人化推薦」section 看到對你的建議。")
        st.session_state.user_city = city
        st.session_state.user_conditions = groups
        st.stop()
    if not target.strip():
        st.error("請填入頻道 ID")
        st.stop()

    city_name = CITY_BY_ID[city]["name"]
    group_labels = [next(g["label"] for g in SENSITIVE_GROUPS if g["id"] == gid) for gid in groups]
    group_text = "、".join(group_labels) if group_labels else "一般族群"

    msg = (
        f"請拉取台灣即時 AQI 並用 2 段繁體中文摘要：① {city_name}（我的城市）目前 AQI、PM2.5 等指標；"
        f"② 對 {group_text} 的具體建議。"
        f"若 {city_name} AQI 低於 {threshold_aqi}，明確說「目前空品良好，無需特別動作」一句帶過。"
        f"必須引用實際抓到的數值。"
    )

    cron_cmd = [
        "openclaw", "cron", "add",
        "--name", f"LobsterAQI-{city}-{threshold_aqi}",
        "--cron", cron_spec[1],
        "--tz", "Asia/Taipei",
        "--session", "isolated",
        "--agent", "analyst",
        "--message", msg,
        "--announce",
        "--channel", channel,
        "--to", target.strip(),
    ]
    cmd_str = " ".join(shlex.quote(p) for p in cron_cmd)

    st.markdown("<div class='eyebrow' style='margin-top:1rem;'>產生的指令</div>", unsafe_allow_html=True)
    st.code(cmd_str, language="bash")

    cA, cB = st.columns(2)
    with cA:
        if st.button("📋 我自己複製到 terminal 跑", use_container_width=True):
            st.info("好，請手動跑上方那行指令。完成後 openclaw cron list 應看得到。")
    with cB:
        if st.button("⚡ 直接幫我註冊（subprocess）", type="primary", use_container_width=True):
            try:
                result = subprocess.run(
                    subprocess.list2cmdline(cron_cmd),
                    shell=True, capture_output=True, text=True, timeout=30,
                    encoding="utf-8", errors="replace",
                )
                if result.returncode == 0:
                    st.success("✓ Cron job 已註冊。執行 `openclaw cron list` 可確認。")
                    st.code(result.stdout[-500:] or "(無輸出)")
                else:
                    st.error(f"註冊失敗（returncode={result.returncode}）")
                    st.code((result.stdout or "") + "\n" + (result.stderr or ""))
            except Exception as e:
                st.error(f"執行錯誤：{type(e).__name__}: {e}")
