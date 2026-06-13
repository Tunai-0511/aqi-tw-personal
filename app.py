"""
🤖 AgentAQI · 台灣空氣品質多代理人監控平台 (Multi-Agent Monitoring Platform)
====================================================================================

這是專案的主程式 — 一個 Streamlit 單頁應用。執行方式:

    streamlit run app.py

頁面架構(由上至下):
  - **頂部封面 (Cover)** :品牌標題 + 「啟動 Pipeline」按鈕 + 模式狀態指示
  - **SECTION · 01 三隻 agent 協作視覺化**:像素風辦公室 + agent 群組聊天室
  - **SECTION · 02 即時 AQI 主儀表板**:時間軸 + 聚焦城市(預設=你的城市)+ 排名 + 地圖 + 散點 + 資料時間
  - **SECTION · 03 24 小時趨勢**:AQI 趨勢線 + 24h×20 城熱力圖 + 7 天紀錄板
  - **SECTION · 04 污染物剖析**:雷達圖 + 堆疊組成
  - **SECTION · 05 環境關聯**:濕度 vs AQI、風玫瑰
  - **SECTION · 06 官方 vs 民間**:EPA 測站對比 CivilIoT / LASS-net 微型感測器
  - **SECTION · 07 健康預警**:預警員為「所選城市」生成詳細個人化建議(可一鍵換城市重生);縣市卡雙層門檻 — 你的城市依你設的閾值、其他縣市依公定 AQI>100,全部未達標顯示 all-clear
  - **SECTION · 08 個人化推薦**:依使用者城市 / 個人健康檔案給個人化健康指數(不再分五大族群)
  - **SECTION · 09 健康日誌**:每日打卡 + 症狀 vs AQI 相關性散點
  - **SECTION · 10 Agent Bot**:Pipeline 匯出 latest_aqi.json 供 Agent Bot(聊天平台)拉取 + 匯出狀態
  - **右下角浮動 AI 助理**:LINE 風格聊天視窗,使用 RAG + LLM 回答問題

核心設計原則:
  1. **State 集中在 `st.session_state`**:`pipeline_done` / `snapshot` / `ts_df` 等
  2. **資料流向**:Pipeline 按鈕 → run_pipeline() → 寫 session_state → 圖表渲染
  3. **無頁面切換**:所有功能在單一 Streamlit script,城市深入是 modal dialog
  4. **真實 API 優先,Mock 兜底**:EPA 失敗才用合成資料,且 UI 標示 MOCK
  5. **自動更新(頁面開著時)**:`st.fragment(run_every="10m")` 每 10 分鐘檢查,
     跨入新的時鐘小時且過整點 10 分(EPA 發布新一輪後)自動重跑 — 對齊 EPA
     整點發布(分頁關閉時不會跑 — Streamlit session 模型)

關鍵 session_state 欄位(完整清單在 init_state 函式):
  - `pipeline_done` : 是否跑過至少一次 Pipeline
  - `snapshot`     : 20 城市當下 AQI 快照 DataFrame
  - `ts_df`        : 24h 時序資料 DataFrame
  - `data_mode`    : "real" 或 "mock"(影響 UI 標示)
  - `chat_history` : AI 助理的對話歷史
  - `rag_chunks`   : RAG 知識庫的所有片段(WHO/EPA/Lancet/上傳 PDF)
  - `last_pipeline_run_at` : 上次 Pipeline 完成時間(自動更新邏輯用)
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from html import escape   # 用於把使用者輸入或 LLM 輸出 escape 後安全嵌入 HTML

import pandas as pd
import streamlit as st

# data 模組:所有資料生成 / API 抓取 / LLM 呼叫的單一入口
from data import (
    AGENTS, CITIES, CITY_BY_ID,
    LLM_PROVIDERS,
    USER_ICD10_OPTIONS,
    aqi_to_level,
    build_agent_payload,
    call_llm_api,
    fetch_citizen_sensors,
    fetch_open_meteo_aq_batch,
    generate_citizen_vs_official,
    generate_current_snapshot,
    generate_real_snapshot,
    generate_real_timeseries,
    generate_time_series,
    parse_agent_c_per_city,
)
import tsdb
# 對接後端是「拉取」模型:Pipeline 跑完把結果匯出成 agent_export/latest_aqi.json,
# 聊天平台的 Agent Bot 讀它回答(本機範例:Hermes/Discord;LINE / Slack / Telegram 皆可)。in-app LLM 仍直接打各家 HTTP API。
from styles import AGENT_STAGE_CSS, DARK_THEME_CSS
# charts 模組:所有 Plotly 圖表工廠
from charts import (
    make_aqi_gauge,
    make_city_ranking,
    make_citizen_vs_official,
    make_heatmap,
    make_humidity_scatter,
    make_map,
    make_pm25_aqi_scatter,
    make_pollutant_radar,
    make_stacked_composition,
    make_trend_line,
    make_wind_rose,
)

# =============================================================================
# 頁面基本設定 (Page setup)
# =============================================================================
# Streamlit 的 `set_page_config` 只能在 script 最頂層呼叫一次,
# 否則會觸發 StreamlitAPIException。
st.set_page_config(
    page_title="AgentAQI · Taiwan Air Quality Multi-Agent System",
    page_icon="🤖",
    layout="wide",                        # 寬版佈局,讓圖表有足夠空間
    initial_sidebar_state="expanded",     # 預設展開 sidebar(設定區)
)
# 注入 CSS:深色主題基底 + 像素辦公室動畫。
# `unsafe_allow_html=True` 允許 raw HTML(預設 Streamlit 會 escape)。
st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)
st.markdown(AGENT_STAGE_CSS, unsafe_allow_html=True)

# =============================================================================
# Session State 初始化 (Session State Init)
# =============================================================================
# Streamlit 每次 rerun 都重新跑整個 script,但 session_state 跨 rerun 保存。
# 這是 Streamlit 唯一能在 rerun 之間保存狀態的機制。
# `init_state()` 在 script 啟動時呼叫一次,把所有需要的 key 設成預設值。
# =============================================================================
def init_state():
    """初始化 st.session_state 的所有預設值。

    `setdefault` 確保:已存在的 key 不會被覆寫(保留使用者已輸入的值),
    新 key 才會被建立。在每次 rerun 都呼叫是安全的。

    所有狀態欄位的含義見 module docstring 與下方逐欄註解。
    """
    defaults = {
        # ── Pipeline 執行狀態 ──
        "pipeline_done":   False,            # 是否跑過至少一次 Pipeline(影響 UI 顯示哪些 section)
        "selected_city":   None,             # 使用者在排名圖點選的城市(聚焦)
        "active_agent":    None,             # Pipeline 跑到哪個 agent(用於高亮 UI)
        "comm_log":        [],               # 3-agent 群組聊天室的訊息歷史

        # ── 自動更新設定 ──
        # 啟用時,fragment 每 10 分鐘檢查;跨入新時鐘小時且過整點緩衝即自動重跑
        # (對齊 EPA 整點發布)。預設 True — 頁面開著一小時後看到的是新鮮資料。
        "auto_refresh_enabled": True,
        "last_pipeline_run_at": None,       # 上次完成 Pipeline 的時間(datetime)

        # ── In-app LLM 設定 ──
        # 直接呼叫各家 LLM HTTP API,毫秒級回應(不經額外的 agent gateway 中介)
        "llm_provider":  "anthropic",        # 預設 Claude
        "llm_key":       "",                 # 使用者貼進來的 API key(本機 session,不上雲)
        "llm_model":     "",                 # 空字串會 fallback 到 LLM_PROVIDERS 的 default_model
        "llm_base_url":  "",                 # 空字串會用 provider 預設 endpoint

        # ── 外部服務金鑰 ──
        "epa_key":                "",        # 環境部 EPA Open Data Token(必填才能拿到真實資料)

        # ── 快照 / 時序資料 ──
        # 都是 DataFrame,Pipeline 跑完才有值。
        "snapshot":        None,             # 20 城市當下快照
        "ts_df":           None,             # 24h 歷史(EPA aqx_p_488 優先,CAMS fallback)
        "cams_ts_df":      None,             # 24h 歷史(CAMS 模型,獨立保留供熱力圖切換)
        "citizen_df":      None,             # 民間 vs 官方 PM2.5 對比 DataFrame
        "lass_cleaning":   None,             # 真實的 LASS 清洗報告 CleaningReport

        # ── 資料模式 ──
        # "real" = EPA API 成功,所有數值是真的
        # "mock" = EPA 失敗 fallback,合成資料,UI 會在頂部顯示 MOCK 警告
        "data_mode":       "mock",

        # ── LLM 輸出快取 ──
        "llm_analysis":    "",               # 分析師(B)的風險分析報告
        "agent_c_advisories": "",            # 預警員(C)的詳細個人化建議:單一城市,程式包成 `<<<CITY:NAME>>>...` sentinel(下游 parse/export 相容)。空字串 = 沒填個人檔案或 LLM 失敗。
        "agent_c_city_id":   None,           # 上面那份建議是針對哪個城市(SECTION 07 顯示 + 判斷要不要提供「換城市重生」)

        # ── RAG 知識庫 ──
        # 預先植入 WHO/EPA/Lancet/MOENV 4 份權威文獻;使用者上傳 PDF 會 append。
        # 詳細運作見 RAG 區段(本檔 L160-294)。
        "rag_chunks":      [],               # 所有 chunk 的 list[dict]
        "rag_files":       [],               # 上傳檔案的 metadata(顯示用)

        # ── 聊天 / UI 狀態 ──
        "chat_history":    [],               # AI 助理對話歷史 list[{"role": "user"/"assistant", "content": "...", ...}]
        "trend_cities":    ["taipei"],       # 趨勢圖預設城市(錨定後=只放你的城市,可再多選比較)
        "radar_cities":    ["taipei", "yunlin", "kaohsiung", "kinmen"],                # 雷達圖預設城市
        # selected_groups 已移除:過去 Section 07 有「敏感族群篩選」按鈕用這個 list,
        # 2026-05-21 改成依個人健康檔案產出每城市個人建議,篩選按鈕一併拿掉。
        "user_city":       "taipei",         # 個人化推薦的「我的城市」
        # 個人 AQI 預警閾值(P1 #1):主畫面會 highlight「你的城市 AQI > 這個門檻」
        "user_aqi_threshold": 100,           # 預設 100(對敏感族群不健康的界線)
        # ── 個人健康檔案(RAG 個人化升級;表單在封面「步驟①」)──
        # 注入 LLM prompt 供分析師 / 預警員 / AI 助理參考
        "user_age":         0,               # 0 = 未提供(刻意非 30:30 會讓 _personal_profile_block 誤判「已填」而永遠把年齡 30 注入 LLM)
        "user_sex":         "prefer_not",    # female / male / other / prefer_not
        "user_height_cm":   165.0,           # 用於計算 BMI(80-230 cm)
        "user_weight_kg":   60.0,            # 用於計算 BMI(20-200 kg)
        "user_diagnoses":   [],              # list of ICD-10 codes(來自 USER_ICD10_OPTIONS)
        "user_med_history": "",              # text_area 病歷重點(使用者自填)
        "user_med_files":   [],              # 已上傳的個人病歷檔 metadata list[{name, n_chunks}]
        "chat_expanded":   False,            # 浮動聊天面板是展開還是收起(FAB)
    }
    # setdefault 而非直接 assignment — 保留使用者已輸入的值
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

init_state()


def _install_hotkey_guard() -> None:
    """擋掉 Streamlit 內建單鍵快捷鍵 C(Clear cache)/ R(Rerun)。

    這兩個快捷鍵在「焦點不在輸入框」時,使用者隨手按到 c / r 就會觸發 —— demo 時
    「Clear caches」對話框一直跳很惱人。用 components.html 在父文件 capture 階段攔截:
    只在『非輸入框焦點 + 無修飾鍵』時吞掉 c / r;在欄位內正常打字完全不受影響。
    用 window 旗標確保只裝一次(components.html 每次 rerun 會重跑,但 listener 只加一次)。
    """
    from streamlit.components.v1 import html as _h
    _h(
        """
        <script>
        (function () {
          const w = window.parent;
          if (!w || w.__botHotkeyGuard) return;
          w.__botHotkeyGuard = true;
          w.document.addEventListener('keydown', function (e) {
            const k = (e.key || '').toLowerCase();
            if ((k === 'c' || k === 'r') && !e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
              const t = e.target, tag = (t && t.tagName || '').toLowerCase();
              const editable = tag === 'input' || tag === 'textarea' || (t && t.isContentEditable);
              if (!editable) { e.stopImmediatePropagation(); e.preventDefault(); }
            }
          }, true);
        })();
        </script>
        """,
        height=0,
    )


_install_hotkey_guard()

# 資料都活在 session_state,run_pipeline() 填入後其他區段才能讀取。


# =============================================================================
# 自動更新心跳 (Auto-refresh Tick) — 對齊 EPA 整點發布
# =============================================================================
# EPA aqx_p_432 每小時發布一輪(整點資料約在整點後幾分鐘上架)。所以自動更新不用
# 「距上次抓取滿 60 分」這種跟著使用者手動時間漂移的節流,而是**對齊時鐘整點**:
#   跨入新的一個小時、且已過整點 EPA_PUBLISH_GRACE_MIN 分鐘(留給 EPA 上架)
#   → 自動重跑 Pipeline 一次。每個「時鐘小時」最多抓一次,API 負載不變。
# fragment 每 10 分鐘醒來檢查(本體只讀幾個 session_state,成本趨近 0),
# 所以實際觸發落在每小時的 HH:10–HH:20 之間 — 剛好接住 EPA 新一輪數據。
# ⚠ Streamlit 是「session 跟著瀏覽器走」的模型:分頁開著(websocket 連線中)
#   fragment 才會定時觸發;分頁關閉 / 電腦休眠就不會跑 — 這不是 bug,是平台特性。
#   需要「關著也更新」要靠外部排程(Windows 工作排程器跑 headless 抓取腳本)。
# =============================================================================
EPA_PUBLISH_GRACE_MIN = 10   # 整點後留給 EPA 上架新一輪資料的緩衝(分鐘)


@st.fragment(run_every="10m")
def _auto_refresh_tick() -> None:
    """每 10 分鐘檢查;跨入新的時鐘小時且過了發布緩衝 → 自動重跑 Pipeline。

    觸發條件(必須全部成立):
      1. 使用者開啟了 sidebar「🔄 自動更新」toggle
      2. Pipeline 已經跑過至少一次(`pipeline_done=True`)— 第一次必須使用者手動啟動
      3. 現在所屬的「時鐘小時」晚於上次抓取所屬的小時(= EPA 已有新一輪資料)
      4. 已過整點 EPA_PUBLISH_GRACE_MIN 分鐘(整點剛過就抓,撈到的常是上一輪)

    觸發後:
      - 設 `_pipeline_should_run=True`(後續主腳本會偵測這個 flag)
      - 用 `st.rerun(scope="app")` 強制全頁重跑(scope="app" 才會跳出 fragment 範圍)
    """
    if not st.session_state.get("auto_refresh_enabled", True):
        return
    if not st.session_state.get("pipeline_done"):
        return  # 沒跑過 Pipeline 不自動啟動;讓使用者第一次手動點(防止冷啟意外消耗 API 配額)
    last = st.session_state.get("last_pipeline_run_at")
    if last is None:
        return
    now = datetime.now()
    crossed_hour = (now.replace(minute=0, second=0, microsecond=0)
                    > last.replace(minute=0, second=0, microsecond=0))
    if crossed_hour and now.minute >= EPA_PUBLISH_GRACE_MIN:
        st.session_state["_pipeline_should_run"] = True
        # 全頁重跑(scope="app")才能觸發後面的 pipeline launch 區段;
        # 預設 scope="fragment" 只會再跑這個 tick 函式,Pipeline 不會被觸發。
        st.rerun(scope="app")


_auto_refresh_tick()  # 註冊 fragment(此呼叫立即返回,fragment 在背景定時觸發)


# =============================================================================
# RAG 知識庫 (Retrieval-Augmented Generation Knowledge Base)
# =============================================================================
# RAG 是「先用關鍵字找出相關文獻片段,再把片段塞進 LLM prompt 當上下文」的技巧,
# 讓 LLM 可以引用權威來源、避免幻覺,並提供可追溯的「引用」。
#
# 本專案的 RAG 是「輕量版」 — 用簡單的 token-overlap 計分(見 `retrieve_rag_chunks`)
# 而非 vector embedding。優點:零依賴、零成本、易理解;缺點:無法處理同義詞。
# 對於「AQI 相關健康問題」這個小型領域已足夠。
#
# 預植入的 4 份權威文獻:
#   1. WHO Air Quality Guidelines 2021     ← 全球公共衛生標準
#   2. US EPA NAAQS                        ← 美國環保署污染標準
#   3. Lancet PM2.5 Cardiovascular 2023    ← 同行評審醫學期刊
#   4. 台灣空氣品質指標技術手冊            ← 台灣官方分級依據
# 使用者也可在 sidebar 上傳 PDF / TXT / MD,內容會被 pdfplumber 抽取成 chunks 後加入。
# =============================================================================

# 預植入的 4 份權威知識(seed snippets)— 系統剛啟動就有的基礎知識
RAG_SNIPPETS = [
    {"source": "WHO Air Quality Guidelines 2021",
     "quote": "PM2.5 年均不應超過 5 μg/m³，24 小時均值不應超過 15 μg/m³；長期暴露與心血管疾病、肺癌風險顯著相關。"},
    {"source": "US EPA NAAQS",
     "quote": "PM2.5 24 小時平均標準為 35 μg/m³，年均標準為 12 μg/m³；AQI > 100 屬於對敏感族群不健康。"},
    {"source": "Lancet PM2.5 Cardiovascular 2023",
     "quote": "高 PM2.5 暴露下進行劇烈戶外運動，肺部沉積量提升 3-5 倍；建議 AQI > 100 時改為室內活動。"},
    {"source": "台灣空氣品質指標技術手冊",
     "quote": "AQI 分六級：良好 (0-50)、普通 (51-100)、對敏感族群不健康 (101-150)、對所有族群不健康 (151-200)、非常不健康 (201-300)、危害 (>300)。"},
]


# ─── PDF / TXT 抽取 helpers ─────────────────────────────────────────────────
# RAG chunk 的資料結構: { "source": str, "text": str, "page": int, "scope": str }
# - source:文獻名 + 頁碼(顯示在引用區)
# - text:該 chunk 的文字內容(400-500 字)
# - page:該 chunk 來自原文的第幾頁
# - scope:"global"(預植入 + sidebar 上傳的通用文獻)或 "personal"(個人病歷)
#         retrieve_rag_chunks 會對 personal 的 chunk 乘 PERSONAL_BOOST(1.4×)加權,
#         讓個人病歷在檢索時優先被命中。
#
# 預植入的 4 份來自 RAG_SNIPPETS;使用者上傳的 PDF/TXT/MD 用 pdfplumber 抽取後 append。
# ─────────────────────────────────────────────────────────────────────────────

# 用兩個換行(段落分隔)切割文字
_PARA_SPLIT_RE = re.compile(r"\n\s*\n+")


def _split_paragraphs(text: str, max_chars: int = 500) -> list[str]:
    """把一頁的文字切成 chunk 大小的段落(~400-500 字)。

    策略 = greedy fill:
      - 短段落整段保留(< max_chars)
      - 超長段落用「。!?」等句尾標點分割,再累積到接近 max_chars 才切

    為什麼是 500 字?
      - 太短(<200):chunk 太多,retrieve 速度慢,且 LLM context 太碎
      - 太長(>800):一個 chunk 涵蓋太多主題,精度下降
      - ~500 字大約對應一個語義段落,平衡 retrieve 精度與 token 預算
    """
    parts: list[str] = []
    for para in _PARA_SPLIT_RE.split(text or ""):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            parts.append(para)
        else:
            # Long para — slice on sentence-ish boundaries
            buf = ""
            for sent in re.split(r"(?<=[。!?！？.])\s*", para):
                if not sent:
                    continue
                if len(buf) + len(sent) > max_chars and buf:
                    parts.append(buf.strip())
                    buf = sent
                else:
                    buf += sent
            if buf.strip():
                parts.append(buf.strip())
    return parts


def _seed_rag_chunks() -> None:
    """確保 session_state.rag_chunks 已植入 4 份權威文獻(idempotent)。

    呼叫時機:
      - sidebar 渲染前(顯示 RAG 知識庫 UI 用)
      - 使用者問 AI 助理時(retrieve_rag_chunks 之前確保有東西可檢索)

    已植入過就直接 return(idempotent 確保不會重複加 4 份)。
    使用者後續上傳的檔案會 append 到同一個 list,不會影響 starter chunks。
    """
    if st.session_state.get("rag_chunks"):
        return
    # 把 RAG_SNIPPETS 轉成 chunk 格式(統一 schema 後 retrieval 邏輯不用分支)
    # scope="global":這些是權威通用文獻,不享有 personal boost 加權
    st.session_state.rag_chunks = [
        {"source": s["source"], "text": s["quote"], "page": 1, "scope": "global"}
        for s in RAG_SNIPPETS
    ]


def _ingest_uploaded_file(f) -> int:
    """處理使用者上傳的 PDF / TXT / MD 檔,抽取內容並加入 rag_chunks。

    PDF 用 pdfplumber 逐頁解析,每頁再切成 ~500 字段落。
    TXT / MD 用 UTF-8 解碼後一樣切段。

    每個 chunk 的 source 會自動加上頁碼,例「report.pdf · 頁 3」,
    讓使用者問問題時,AI 引用區塊可以精確指向原文位置。

    Returns
    -------
    int
        新增的 chunk 數量(用於 sidebar 顯示「已加入 X 段」回饋)
    """
    name = f.name.lower()
    added = 0
    try:
        if name.endswith(".pdf"):
            import pdfplumber
            with pdfplumber.open(f) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    for para in _split_paragraphs(text):
                        st.session_state.rag_chunks.append({
                            "source": f"{f.name} · 頁 {i}",
                            "text":   para,
                            "page":   i,
                            "scope":  "global",
                        })
                        added += 1
        else:  # .txt / .md / anything else read as utf-8 text
            raw = f.read()
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raw = raw.decode("utf-8", errors="replace")
            for para in _split_paragraphs(raw):
                st.session_state.rag_chunks.append({
                    "source": f.name,
                    "text":   para,
                    "page":   1,
                    "scope":  "global",
                })
                added += 1
    except Exception as e:
        st.warning(f"無法解析 {f.name}：{type(e).__name__}: {e}")
    return added


def _ingest_personal_medical_file(f) -> int:
    """處理使用者上傳的「個人病歷」檔,標記為 scope="personal"。

    走和 `_ingest_uploaded_file` 同一條 pdfplumber 解析路徑,但:
      - 每個 chunk 的 source 前綴 "[個人病歷] "(視覺上明顯區分)
      - scope 改為 "personal" → retrieve_rag_chunks 會給 1.4× 加權
      - 在 st.session_state.user_med_files 寫入一筆 metadata,
        供封面「步驟①」UI 顯示「已上傳 X 份個人病歷」以及清除按鈕使用。

    Returns
    -------
    int
        新增的 chunk 數量
    """
    # 記住開始時的 chunk index,結束後把這段新增的 chunks 改 scope + 加 prefix
    start_idx = len(st.session_state.rag_chunks)
    added = _ingest_uploaded_file(f)
    if added > 0:
        for c in st.session_state.rag_chunks[start_idx:]:
            c["scope"]  = "personal"
            c["source"] = f"[個人病歷] {c['source']}"
        st.session_state.user_med_files.append({
            "name":     f.name,
            "n_chunks": added,
        })
    return added


def _score_chunk(query: str, chunk_text: str) -> float:
    """計算 chunk_text 與 query 的相關度分數。

    演算法:**2-char n-gram overlap**(字元級雙連字符重疊)
      - 不需要分詞器(tokenizer)就能處理中英文混排
      - 把 query 切成相鄰兩字元的集合,例「PM2.5 對心血管」→ {"PM", "M2", "2.", ".5", ...}
      - 計算 chunk 中有多少 n-gram 出現在 query 集合中
      - 用 √len(c) 標準化,避免短 chunk 因為總命中數少而被低估

    為什麼不用 embedding?
      - 零依賴,不需要 sentence-transformers 等模型(節省幾百 MB 下載)
      - 對「AQI 健康問題」這個小型領域,字元 overlap 已夠用
      - 缺點是不能處理同義詞(例「心血管」vs「心臟」會被當不同字串)
    """
    q = (query or "").lower()
    c = (chunk_text or "").lower()
    if len(q) < 2 or len(c) < 2:
        return 0.0
    # 用 set 去重 — 「AAAA」不會因為有 3 個 AA 就被加權 3 倍
    qgrams = {q[i:i+2] for i in range(len(q) - 1)}
    if not qgrams:
        return 0.0
    hits = sum(1 for i in range(len(c) - 1) if c[i:i+2] in qgrams)
    # 長度標準化:對長度開根號,避免「過短 chunk 永遠贏」或「長 chunk 永遠輸」
    return hits / (len(c) ** 0.5)


def retrieve_rag_chunks(query: str, top_k: int = 5) -> list[dict]:
    """從所有 RAG chunks 中找出與 query 最相關的 top_k 個。

    這是 RAG 流程的核心:LLM 收到使用者問題前,先用本函式檢索文獻片段,
    把片段拼成 prompt 的 context,讓 LLM 有「資料可引用」、減少幻覺。

    Fallback 策略:若沒有任何 chunk 分數 > 0(query 完全沒命中任何文獻),
    退回前 4 個 starter chunks(WHO/EPA/Lancet/MOENV),確保 LLM 總有
    至少 4 份權威來源可以參考,而不是 zero-context 自由發揮。

    Parameters
    ----------
    query : str
        使用者的問題
    top_k : int
        最多回傳幾個 chunks(預設 5,平衡引用品質與 token 預算)

    Returns
    -------
    list[dict]
        list of {"source", "text", "page"}
    """
    chunks = st.session_state.get("rag_chunks") or []
    if not chunks:
        return []
    # 對每個 chunk 計分;scope=="personal" 乘 1.4× 加權,讓使用者上傳的個人病歷
    # 在檢索時優先被命中(個人病歷與使用者問題語境最相關,但通常字數較少,
    # 不加權會被長篇通用文獻擠下排名)。
    PERSONAL_BOOST = 1.4
    scored = []
    for c in chunks:
        s = _score_chunk(query, c["text"])
        if c.get("scope") == "personal":
            s *= PERSONAL_BOOST
        scored.append((c, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    # 只保留有命中的(score > 0);若全 miss 則回 starter chunks 確保 LLM 有上下文
    top = [c for c, s in scored[:top_k] if s > 0]
    return top if top else chunks[: min(top_k, 4)]

# =============================================================================
# 多代理人輔助函式 (Multi-agent Helpers)
# =============================================================================
def agent_name(agent_id: str) -> str:
    """根據 agent id 查回中文名(失敗時直接回傳 id)。"""
    return next((a["name"] for a in AGENTS if a["id"] == agent_id), agent_id)


# 多代理人群組聊天室的「參與者清單」。
# 每個 agent 用一個 dict 表示:
#   name   中文名(顯示在聊天室訊息開頭)
#   label  小型 emoji icon(畫在圓形頭像泡泡中,提示該 agent 的工作性質)
#   color  主題色(訊息泡泡邊框、頭像背景)
# 一目了然比抽象的 A/B/C 字母更友善。
PARTICIPANTS: dict[str, dict[str, str]] = {
    "A":       {"name": "採集者",       "label": "📡", "color": "#00d9ff"},
    "B":       {"name": "分析師",       "label": "🧠", "color": "#9b59ff"},
    "C":       {"name": "預警員",       "label": "🏥", "color": "#00e676"},
    "SYS":     {"name": "系統",         "label": "⚙",  "color": "#8b95a8"},
    "LLM":     {"name": "LLM",          "label": "🤖", "color": "#c4a5ff"},
    "DB":      {"name": "本機時序快取", "label": "💾", "color": "#4eecff"},
    "EXPORT":  {"name": "JSON 匯出",    "label": "📦", "color": "#ffb380"},
    "USER":    {"name": "使用者",       "label": "👤", "color": "#e8eef7"},
    "*":       {"name": "全體 agent",   "label": "📢", "color": "#c0c8d8"},
}


def _participant(pid: str) -> dict[str, str]:
    return PARTICIPANTS.get(pid, {"name": pid, "label": "?", "color": "#c0c8d8"})


def push_log(agent_id: str, msg: str, to: str = "SYS"):
    """把一則「agent 對話」訊息加進群組聊天室 log。

    Pipeline 跑各個階段時,會用本函式記錄「誰對誰說了什麼」,例如:
      push_log("A", "拉到 EPA 即時資料", to="SYS")
      push_log("B", "風險分析完成,轉交預警員", to="C")
    這些訊息會即時顯示在主畫面右側的「🤖 #aqi-agents 群組聊天室」。

    Parameters
    ----------
    agent_id : str
        發送者代號(A/B/C/SYS/LLM/DB/EXPORT/USER)
    msg : str
        訊息內容(可含 emoji)
    to : str
        收件者代號;'*' 表示廣播給所有 agent
    """
    now = datetime.now().strftime("%H:%M:%S")
    st.session_state.comm_log.append({
        "time":  now,
        "agent": agent_id,
        "to":    to,
        "msg":   msg,
    })


def _render_chat_row(entry: dict) -> str:
    """Render one chat-bubble row in the group-chat style."""
    src = _participant(entry["agent"])
    dst = _participant(entry.get("to", "SYS"))
    is_system_target = entry.get("to") in ("SYS", "") or entry.get("to") is None

    if is_system_target:
        # No arrow shown — internal status
        meta = (
            f"<span class='chat-from' style='color:{src['color']};'>{escape(src['name'])}</span>"
            f"<span class='chat-meta-sep'>·</span>"
            f"<span class='chat-sys-tag'>系統訊息</span>"
            f"<span class='chat-time'>{entry['time']}</span>"
        )
    else:
        meta = (
            f"<span class='chat-from' style='color:{src['color']};'>{escape(src['name'])}</span>"
            f"<span class='chat-arrow'>→</span>"
            f"<span class='chat-to' style='color:{dst['color']};'>{escape(dst['name'])}</span>"
            f"<span class='chat-time'>{entry['time']}</span>"
        )

    return (
        f"<div class='chat-msg-row'>"
        f"<div class='chat-avatar' style='background:{src['color']}; box-shadow:0 0 8px {src['color']}88;'>{src['label']}</div>"
        f"<div class='chat-body'>"
        f"<div class='chat-meta'>{meta}</div>"
        f"<div class='chat-text'>{escape(entry['msg'])}</div>"
        f"</div>"
        f"</div>"
    )


def _log_render(log_holder) -> None:
    rows = "".join(_render_chat_row(e) for e in st.session_state.comm_log[-12:])
    log_holder.markdown(f"<div class='chat-room'>{rows}</div>", unsafe_allow_html=True)


# ── Live-paint helpers for the agent theater ─────────────────────────────────
# These build HTML from current session_state and write it into a placeholder
# (st.empty()) that the section pre-allocates. The same helpers are called by
# (a) the section itself on initial render (idle state), and (b) `run_pipeline`
# after every push_log so the user sees bubbles flow agent-by-agent in real time.

# Which session-state field holds each agent's real LLM dialogue output.
# Used by `_build_office_html` to decide what the speech bubble should show
# AFTER the pipeline finishes — we want real dialog content, not stale
# transfer-of-data plumbing messages from comm_log.
_AGENT_SUMMARY_FIELD: dict[str, str] = {
    # 採集者 (A) is a pure ETL phase — no LLM summary. Its bubble stays empty
    # after the pipeline finishes (the cleaning card below tells its story).
    "B": "llm_analysis",
    "C": "agent_c_advisories",
}


def _bubble_preview(text: str) -> str:
    """從 agent 輸出抓一段適合貼在 desk speech bubble 上的「人讀」摘要。

    Agent C 改版後輸出格式是 `<<<CITY:NAME>>>...` sentinel,直接 truncate
    前 220 字 bubble 會顯示成 `<<<CITY:台北市>>>` 完全沒資訊。本 helper:
      1. 拿掉所有 `<<<CITY:...>>>` sentinel
      2. 拿掉開頭的 markdown headings(`#`/`##`/`###`)
      3. 取第一段非空白文字
    Agent B 的 llm_analysis 沒有這些 markup,helper 對它是 no-op。
    """
    if not text:
        return ""
    cleaned = re.sub(r"<<<CITY:[^>]*>>>", " ", text)
    # 把 markdown heading 行的 `#` 前綴拿掉(留標題文字)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    # 取第一段非空白文字
    for line in cleaned.split("\n"):
        line = line.strip()
        if line:
            return line
    return ""


def _build_office_html(active_id: str | None) -> str:
    last_msg: dict[str, str] = {}
    for entry in st.session_state.comm_log:
        last_msg[entry["agent"]] = entry["msg"]
    pipe_done = st.session_state.pipeline_done
    parts: list[str] = []
    for ag in AGENTS:
        is_active = (active_id == ag["id"])

        # Bubble content rules:
        #   - Live: agent currently active → latest push_log message
        #   - Done: pipeline finished       → agent's real LLM summary (if any)
        #   - Idle: no active, not done     → empty bubble
        # This makes the speech bubble feel like real dialog — if no actual
        # LLM dialog happened, no bubble shows.
        if is_active:
            bubble_msg = last_msg.get(ag["id"], "")
        elif pipe_done:
            field = _AGENT_SUMMARY_FIELD.get(ag["id"], "")
            raw = (st.session_state.get(field) or "").strip() if field else ""
            # 預警員(C)輸出是 <<<CITY:NAME>>> sentinel 格式,直接 truncate
            # 會在 bubble 上顯示亂碼。用 _bubble_preview 拿到可讀的第一段。
            bubble_msg = _bubble_preview(raw) if raw else ""
        else:
            bubble_msg = ""

        has_msg = bool(bubble_msg)
        bubble_class = "bubble" if has_msg else "bubble empty"
        # Glow the bot + monitor when active OR when there's a real
        # post-pipeline summary to show.
        is_visually_active = is_active or (pipe_done and has_msg)
        bot_class = "bot active" if is_visually_active else "bot"
        mon_class = "monitor active" if is_visually_active else "monitor"
        # Truncate to keep DOM small; CSS line-clamp handles the visual
        # 2-line cap. 220 chars is well above the 2-line visible budget.
        display = escape(bubble_msg[:220]) if has_msg else "&nbsp;"
        parts.append(
            f"<div class='desk' style='--agent-color:{ag['color']}; --agent-glow:{ag['color']}; --bubble-color:{ag['color']}; --bubble-glow:{ag['color']}55;'>"
            f"<div class='{bubble_class}'>{display}</div>"
            f"<div class='{bot_class}'>🤖</div>"
            f"<div class='desk-base'></div>"
            f"<div class='{mon_class}'>{ag['id']}</div>"
            f"<div class='agent-label'>{ag['name']}</div>"
            f"<div class='agent-role'>{ag['role']}</div>"
            f"<div class='agent-desc'>{ag['desc']}</div>"
            f"</div>"
        )
    return f"<div class='office'>{''.join(parts)}</div>"


# NOTE: _build_critic_html removed in the 3-agent refactor — the Critic
# agent's grading was decorative (low scores didn't gate anything).


def _build_cleaning_html() -> str:
    cleaning = st.session_state.get("lass_cleaning")
    if cleaning is None:
        return (
            "<div class='clean-card' style='opacity:0.55;'>"
            "<div class='head'>🧹 民間感測清洗報告</div>"
            "<div style='font-size:0.85rem; color:#8b95a8; padding:0.4rem 0;'>"
            "Pipeline 尚未執行 — 民間感測員啟動後會即時拉取民生公共物聯網 + LASS-net 資料，"
            "並把實際清洗結果（原始 / 保留 / 丟棄筆數）顯示在這裡。"
            "</div></div>"
        )
    drops = "".join(
        f"<span class='tag orange'>{escape(k)} {v}</span>"
        for k, v in cleaning.drop_reasons.items()
    )
    return f"""
<div class='clean-card'>
  <div class='head'>🧹 民間感測清洗報告（民生公共物聯網 + LASS-net）</div>
  <div style='display:flex; gap:1.4rem; align-items:center;'>
    <div>
      <div class='tiny muted'>原始</div>
      <div style='font-family:JetBrains Mono; font-size:1.6rem; font-weight:800; color:#8b95a8;'>{cleaning.raw_records}</div>
    </div>
    <div style='color:#4a5266; font-size:1.4rem;'>→</div>
    <div>
      <div class='tiny muted'>保留</div>
      <div style='font-family:JetBrains Mono; font-size:1.6rem; font-weight:800; color:#00e676;'>{cleaning.kept_records}</div>
    </div>
    <div style='color:#4a5266; font-size:1.4rem;'>×</div>
    <div>
      <div class='tiny muted'>丟棄</div>
      <div style='font-family:JetBrains Mono; font-size:1.6rem; font-weight:800; color:#ff4757;'>{cleaning.dropped_records}</div>
    </div>
    <div style='flex:1; text-align:right;'>
      <div class='tiny muted'>保留率</div>
      <div style='font-family:JetBrains Mono; font-size:1.6rem; font-weight:800; color:#ff8c42;'>{cleaning.keep_rate * 100:.1f}%</div>
    </div>
  </div>
  <div style='margin-top:0.8rem; display:flex; gap:0.4rem; flex-wrap:wrap;'>{drops}</div>
</div>
"""


def _build_chat_log_html() -> str:
    if not st.session_state.comm_log:
        return (
            "<div class='chat-room' style='text-align:center; color:#4a5266; padding:2rem;'>"
            "點擊上方 <b style='color:#00d9ff;'>「啟動三代理人 Pipeline」</b> 加入群組聊天室"
            "</div>"
        )
    rows = "".join(_render_chat_row(e) for e in st.session_state.comm_log[-25:])
    return f"<div class='chat-room' style='max-height:520px;'>{rows}</div>"


def _paint_office(ph, active_id: str | None = None) -> None:
    ph.markdown(_build_office_html(active_id), unsafe_allow_html=True)


# _paint_critic removed alongside _build_critic_html (3-agent refactor).


def _paint_cleaning(ph) -> None:
    ph.markdown(_build_cleaning_html(), unsafe_allow_html=True)


def _paint_chat(ph) -> None:
    ph.markdown(_build_chat_log_html(), unsafe_allow_html=True)


# =============================================================================
# Agent Bot JSON 匯出(拉取模型)— Pipeline 跑完寫 agent_export/latest_aqi.json,
# 聊天平台 Agent Bot 讀它回答(本機範例:Hermes/Discord)。取代舊的 webhook 推送。
# =============================================================================
def _persona_dict():
    """把使用者個人健康檔案組成結構化 dict(供 JSON 匯出);完全沒填回 None。

    「有沒有填」的判準(年齡>0 / 有診斷 / 有病歷)。封面步驟①填好後,Pipeline 第一次
    跑就會把它一起匯出給 Hermes。改版後不再用五大族群,個人化以年齡 / BMI / 診斷為準。
    """
    age   = int(st.session_state.get("user_age", 0) or 0)
    diags = st.session_state.get("user_diagnoses", []) or []
    hist  = (st.session_state.get("user_med_history") or "").strip()
    if not (age or diags or hist):
        return None
    bmi, bmi_cat = _calc_bmi(
        st.session_state.get("user_height_cm", 0) or 0,
        st.session_state.get("user_weight_kg", 0) or 0,
    )
    diag_labels = [
        f"{d['label']}（{d['code']}）"
        for d in USER_ICD10_OPTIONS if d["code"] in diags
    ]
    sex_label = {"female": "女", "male": "男", "other": "其他",
                 "prefer_not": "未提供"}.get(
        st.session_state.get("user_sex", "prefer_not"), "未提供")
    return {
        "age":          age,                 # 0 = 未提供
        "sex":          sex_label,
        "bmi":          round(bmi, 1),
        "bmi_category": bmi_cat,
        "diagnoses":    diag_labels,
        "med_history":  hist,
        "city":         st.session_state.get("user_city", "taipei"),
        "threshold":    int(st.session_state.get("user_aqi_threshold", 100)),
    }


def _write_agent_export(snapshot_df):
    """把這次 Pipeline 結果寫成 agent_export/latest_aqi.json(Agent Bot 拉取用)。回傳 Path。"""
    from pathlib import Path
    payload = build_agent_payload(
        snapshot_df,
        analysis=st.session_state.get("llm_analysis", ""),
        advisories_raw=st.session_state.get("agent_c_advisories", ""),
        data_mode=st.session_state.get("data_mode", "mock"),
        user_city=st.session_state.get("user_city", "taipei"),
        threshold=int(st.session_state.get("user_aqi_threshold", 100)),
        user_profile=_persona_dict(),
    )
    out_dir = Path(__file__).resolve().parent / "agent_export"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "latest_aqi.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


# ── 預警員(Agent C)的 prompt 工廠 + 單獨重生 ─────────────────────────────
# 改版:預警員從「20 城市各 3-4 句」改成「只針對所選城市,一份分節的詳細建議」。
# 理由:(a) 深度 — 單城市可以寫到 250-450 字、分 5 小節,而不是每城 3 句蜻蜓點水;
#       (b) 成本 — LLM token 省 ~20 倍、生成時間大幅縮短;
#       (c) 彈性 — 點「城市排行」換聚焦後,SECTION 07 可一鍵只為新城市重生。
# 模型輸出純文字(不再要求 sentinel),程式自己包一層 <<<CITY:NAME>>> —— 下游的
# parse_agent_c_per_city / Hermes 匯出 / 城市 modal 全部不用改。
_ADVISOR_SYSTEM = (
    "你是台灣空氣品質系統的健康預警員。重要:只能根據訊息中提供的具體數值與文獻作答,"
    "禁止編造資料、城市或事件。回覆使用繁體中文。"
)


def _advisor_prompt_for_city(snapshot_df, city_id: str):
    """組「單一城市 × 詳細個人化建議」的預警員 prompt。

    Returns (prompt, city_row);使用者沒填個人檔案時回 (None, None)。
    城市不在快照時 fallback 到當下最高 AQI 城市(理論上不會發生)。
    """
    prof = _personal_profile_block()
    if not prof:
        return None, None
    match = snapshot_df[snapshot_df["city_id"] == city_id]
    if match.empty:
        match = snapshot_df.sort_values("aqi", ascending=False).head(1)
    row = match.iloc[0]
    rank = int((snapshot_df["aqi"] > row["aqi"]).sum()) + 1
    avg_aqi = float(snapshot_df["aqi"].mean())
    # 個人 RAG(scope=personal 享 1.4× boost):query 用診斷標籤 + 目標城市
    try:
        _seed_rag_chunks()
        diag_labels = [
            d["label"] for d in USER_ICD10_OPTIONS
            if d["code"] in st.session_state.get("user_diagnoses", [])
        ]
        picked = retrieve_rag_chunks(
            "個人健康建議 " + " ".join(diag_labels) + " " + str(row["city"]), top_k=5
        )
    except Exception:
        picked = []
    rag_block = ""
    if picked:
        rag_block = (
            "\n=== RAG 檢索結果(可引用,標註來源)===\n"
            + "\n".join(f"  [{c['source']}] {c['text']}" for c in picked)
            + "\n"
        )
    prompt = (
        prof + "\n"
        f"你是空品健康預警員。只針對「{row['city']}」這一個城市,為上面這位使用者寫一份**詳細**的個人化健康建議。\n\n"
        f"=== {row['city']} 即時數據 ===\n"
        f"AQI {row['aqi']:.0f}({row['level']})· PM2.5 {row['PM2.5']} μg/m³ · PM10 {row['PM10']} · "
        f"O3 {row['O3']} · NO2 {row['NO2']} · SO2 {row['SO2']} · CO {row['CO']}\n"
        f"全國脈絡:全國平均 AQI {avg_aqi:.0f};{row['city']} 在 20 城市中第 {rank} 高。\n"
        f"對照使用者自設閾值:目前 AQI {row['aqi']:.0f} "
        f"{'已超過' if float(row['aqi']) > int(st.session_state.get('user_aqi_threshold', 100)) else '未超過'}"
        f"使用者設定的 {int(st.session_state.get('user_aqi_threshold', 100))} — 建議必須回應這一點。\n"
        + rag_block
        + "\n=== 輸出格式(繁體中文,總長 250-450 字,依下列小節,不要其他前言)===\n"
        "【現況風險】2-3 句:此刻對這位使用者的主要風險與原因,引用具體數值與其年齡/疾病\n"
        "【外出建議】2-3 句:今天適不適合出門、建議的活動強度/時段/時長\n"
        "【防護裝備】1-2 句:口罩等級、是否開空氣清淨機、其他防護\n"
        "【症狀警訊】1-2 句:出現哪些症狀該中止活動或就醫(對應其病史)\n"
        "【一句總結】20 字內的行動指令\n"
        "規則:只引用上面提供的數值與文獻,不可編造;若 RAG 有個人病歷內容請帶到。"
    )
    return prompt, row


def _regen_advisor_for_city(snapshot_df, city_id: str) -> str | None:
    """SECTION 07「🔁 重新產生」:單獨呼叫一次預警員 LLM。成功回 None,失敗回原因字串。"""
    prompt, row = _advisor_prompt_for_city(snapshot_df, city_id)
    if prompt is None:
        return "請先在封面「步驟①」填寫個人健康檔案"
    if not st.session_state.get("llm_key"):
        return "sidebar 尚未填 LLM 金鑰"
    resp = call_llm_api(
        st.session_state.llm_provider, st.session_state.llm_key, prompt,
        st.session_state.llm_model, st.session_state.llm_base_url,
        system=_ADVISOR_SYSTEM, max_tokens=3072, timeout=120,
    )
    if not resp:
        import data as _data
        return "LLM 失敗:" + (getattr(_data, "LAST_LLM_ERROR", "") or "未知原因")
    st.session_state.agent_c_advisories = f"<<<CITY:{row['city']}>>>\n{resp.strip()}\n"
    st.session_state.agent_c_city_id = str(row["city_id"])
    return None


def run_pipeline(
    office_ph=None,
    cleaning_ph=None,
    chat_ph=None,
    progress_ph=None,
    status_ph=None,
):
    """執行 3-agent Pipeline(採集者 → 分析師 → 預警員)並即時更新 UI。

    這是整個應用的「核心執行函式」 — 使用者按下「啟動 Pipeline」按鈕後
    就會觸發本函式。函式體內依序執行:

      A. **採集者** (Collector) — 純 ETL,無 LLM
         1. 拉 EPA 即時資料 (fetch_epa_realtime)
         2. 並行拉氣象 (5 個區域代表城市)
         3. 並行拉民間感測器 (CivilIoT + LASS,清洗去重)
         4. 整合成 snapshot DataFrame + ts_df 時序

      B. **分析師** (Analyst) — 用 LLM 寫風險分析報告
         1. 從 RAG 檢索與 AQI 等級相關的文獻片段
         2. 組合 prompt:「全國均值 + 最高/最低城市 + RAG context」
         3. 呼叫 LLM (call_llm_api),把回應存到 `llm_analysis`

      C. **預警員** (Advisor) — 用 LLM 產出「個人化」健康建議
         1. 先檢查使用者有沒有填封面「步驟①」個人健康檔案;沒填則完全跳過 LLM 呼叫
            (省 token,UI 改顯示 CTA banner)
         2. 有填:只為「所選城市」生成一份 5 小節詳細建議(prompt 由
            _advisor_prompt_for_city 統一組;注入 personal-scope RAG 病歷)
         3. 輸出由程式包成 `<<<CITY:NAME>>>` sentinel 存到 `agent_c_advisories`,
            UI / 匯出用 `parse_agent_c_per_city()` 拆 dict(單城市一筆)

      整批寫入 SQLite tsdb(時序快取),供「過去 7 天」紀錄板使用。
      最後把結果匯出成 agent_export/latest_aqi.json,供聊天平台 Agent Bot 拉取(本機範例:Hermes/Discord)。

    Parameters
    ----------
    *_ph : st.empty | None
        外部呼叫者(agent section)預先建立的 placeholder,讓 live update
        直接寫到該位置而不是浮在頁面任意地方。None 則 fallback 到本地 st.empty。

    歷史:早期 5-agent 設計有「D 民間感測員」與「Critic 品管員」,但 D 的
    LLM 註解沒有下游使用 → 併入採集者;Critic 評分沒有 gate 任何 retry
    → 移除。3-agent 重構讓邏輯更清晰。
    """
    st.session_state.comm_log              = []
    st.session_state.pipeline_done         = False
    st.session_state.snapshot              = None
    st.session_state.llm_analysis          = ""
    st.session_state.agent_c_advisories    = ""
    st.session_state.agent_c_city_id       = None

    # If the caller (the agent section) pre-allocated placeholders, route all
    # live updates there — that's how the chat log ends up inside the
    # theater area instead of floating between cover and section.
    # `progress_ph=None` is a deliberate "no visible progress bar" mode —
    # the status pill + chat log + office bubble updates already give the
    # user plenty of feedback, the bar was redundant noise on a busy page.
    class _SilentProgress:
        def progress(self, *args, **kwargs):
            return self
    if progress_ph is None:
        progress = _SilentProgress()
    else:
        progress = progress_ph.progress(0.0, text="正在啟動代理人...")
    log_holder    = chat_ph    if chat_ph    is not None else st.empty()
    status_holder = status_ph  if status_ph  is not None else st.empty()
    _office_ph    = office_ph
    _cleaning_ph  = cleaning_ph

    # Convenience: repaint pixel office after every active_agent change.
    # `_refresh_log` does chat-log + theater in one call, since the two
    # should always stay in sync during a pipeline run.
    def _refresh_theater() -> None:
        if _office_ph is not None:
            _paint_office(_office_ph, st.session_state.active_agent)

    def _refresh_log() -> None:
        _log_render(log_holder)
        _refresh_theater()

    def _refresh_cleaning() -> None:
        if _cleaning_ph is not None:
            _paint_cleaning(_cleaning_ph)

    # Initial sync so the office reflects "starting up" state immediately.
    _refresh_theater()

    # Direct LLM config (no agent-gateway routing — much faster than plugin discovery)
    llm_provider = st.session_state.llm_provider
    llm_key      = st.session_state.llm_key.strip()
    llm_model    = st.session_state.llm_model or LLM_PROVIDERS[llm_provider]["default_model"]
    llm_base_url = st.session_state.llm_base_url
    has_llm      = bool(llm_key)
    prov_name    = LLM_PROVIDERS[llm_provider]["name"]

    AGENT_SYSTEM = (
        "你是台灣空氣品質多代理人系統中的一員。重要：只能根據訊息中提供的具體數值作答，"
        "禁止編造資料、城市或事件。回覆使用繁體中文，不限制長度——把該講的講完整。"
    )

    def _agent_llm(prompt: str, max_tokens: int = 4096, system: str | None = None) -> tuple[str | None, str]:
        """Direct provider call. Returns (response_or_None, error_reason).
        error_reason is empty on success, otherwise a short diagnostic string."""
        if not has_llm:
            return None, "未填 LLM 金鑰"
        resp = call_llm_api(
            llm_provider, llm_key, prompt, llm_model, llm_base_url,
            system=system or AGENT_SYSTEM, max_tokens=max_tokens, timeout=120,
        )
        if resp:
            return resp, ""
        # call_llm_api wrote the reason into data.LAST_LLM_ERROR
        import data as _data
        return None, getattr(_data, "LAST_LLM_ERROR", "") or "未知失敗"

    def _status(agent_id: str, done: bool = False) -> None:
        if done:
            status_holder.markdown(
                "<span class='pill green'><span class='dot'></span>Pipeline 完成</span>",
                unsafe_allow_html=True,
            )
        else:
            tag = prov_name if has_llm else "Fallback"
            status_holder.markdown(
                f"<span class='pill cyan'><span class='dot'></span>{agent_name(agent_id)} 執行中 · {escape(tag)}</span>",
                unsafe_allow_html=True,
            )

    # ── 採集者 (A) ──────────────────────────────────────────────────────
    # Pure data fetching + cleaning. No LLM call. Pulls 3 sources:
    #   1. 環境部 EPA aqx_p_432 + Open-Meteo weather (per-region)
    #   2. 民生公共物聯網 SensorThings + LASS-net Airbox (parallel)
    #   3. Civic-vs-official PM2.5 comparison frame
    # Previously this was split across 2 agents (A + D), with both doing a
    # vestigial "comment on data quality" LLM call that the rest of the
    # pipeline never used. The 3-agent refactor merged them and dropped the
    # LLM grading — 採集者 is now a pure ETL phase.
    st.session_state.active_agent = "A"
    progress.progress(0.05, text="採集者 · 資料採集中...")
    _status("A")

    if has_llm:
        push_log("SYS", f"{prov_name} 金鑰已就緒，啟動 3-agent Pipeline", to="*")
    else:
        push_log("SYS", "未填 LLM 金鑰，分析師/預警員段落將跳過（圖表照常產生）", to="*")
    _refresh_log()
    time.sleep(0.2)

    # 1. 環境部 EPA 即時 + Open-Meteo 氣象
    push_log("A", "呼叫環境部 EPA aqx_p_432 抓 20 城市測站", to="SYS")
    _refresh_log()
    snapshot, status_msg = generate_real_snapshot(st.session_state.epa_key or None)
    if snapshot is not None:
        push_log("SYS", f"回傳 → {status_msg}", to="A")
        push_log("A", "Open-Meteo 氣象已合併（溫度／濕度／氣壓）", to="SYS")
        ts_df = generate_real_timeseries(snapshot, hours_back=24, epa_key=st.session_state.epa_key or None)
        st.session_state.data_mode = "real"
    else:
        push_log("SYS", f"⚠ {status_msg}，改用內建模擬資料", to="A")
        snapshot = generate_current_snapshot()
        ts_df    = generate_time_series(24)
        st.session_state.data_mode = "mock"

    st.session_state.snapshot = snapshot
    st.session_state.ts_df    = ts_df
    progress.progress(0.20, text="採集者 · EPA 完成")
    _refresh_log()

    # 2. 民生公共物聯網 + LASS-net (parallel)
    push_log("A",
             "並行拉取 民生公共物聯網 SensorThings (sta.colife.org.tw/STA_AirQuality_EPAIoT) "
             "+ LASS-net Airbox",
             to="SYS")
    _refresh_log()
    lass_df, lass_cleaning, lass_status = fetch_citizen_sensors()
    if lass_df is not None and lass_cleaning is not None:
        push_log("SYS", f"回傳 → {lass_status}", to="A")
        push_log("A",
                 f"清洗：原始 {lass_cleaning.raw_records} 筆 → 保留 {lass_cleaning.kept_records} 筆 · "
                 f"丟棄 {lass_cleaning.dropped_records} 筆（保留率 {lass_cleaning.keep_rate*100:.1f}%）",
                 to="SYS")
        push_log("A",
                 "丟棄原因 · " + " / ".join(
                     f"{k} {v}" for k, v in lass_cleaning.drop_reasons.items()
                 ),
                 to="SYS")
        st.session_state.lass_cleaning = lass_cleaning
        st.session_state.citizen_df    = generate_citizen_vs_official(snapshot, lass_df)
        covered = int((st.session_state.citizen_df["sensor_count"] > 0).sum())
        push_log("A",
                 f"對應 {covered}/{len(CITIES)} 城市有民間感測站覆蓋（離島放寬到 20 km 半徑）",
                 to="SYS")
    else:
        push_log("SYS", f"⚠ 民間感測 API 失敗 - {lass_status}。略過民間感測對比", to="A")
        st.session_state.lass_cleaning = None
        st.session_state.citizen_df    = generate_citizen_vs_official(snapshot, None)
    _refresh_log()
    _refresh_cleaning()

    # 計算給 B 用的快速統計
    avg_aqi_pipe = snapshot["aqi"].mean()
    worst_pipe   = snapshot.sort_values("aqi", ascending=False).iloc[0]
    best_pipe    = snapshot.sort_values("aqi").iloc[0]

    push_log("A",
             f"資料封包完成 → 傳送 {len(snapshot)} 城市官方資料 + "
             f"{(lass_cleaning.kept_records if lass_cleaning else 0)} 筆民間感測 + 24h 歷史",
             to="B")
    _refresh_log()
    progress.progress(0.45, text="採集者 · 完成")


    # ── AGENT B ─────────────────────────────────────────────────────────────
    st.session_state.active_agent = "B"
    _status("B")
    push_log("B", "收到採集者與民間感測員的資料封包，開始綜合分析", to="*")
    _refresh_log()
    time.sleep(0.3)
    push_log("B", "RAG 檢索：WHO 2021、EPA NAAQS、Lancet 2023", to="SYS")
    _refresh_log()
    time.sleep(0.35)

    if has_llm:
        push_log("B", f"請 {prov_name} 生成 3 段風險分析報告", to="LLM")
        _refresh_log()
        # 注入個人 profile(若使用者沒填則為空字串,零回歸)
        b_profile = _personal_profile_block()
        b_profile_section = (b_profile + "\n") if b_profile else ""
        b_resp, b_err = _agent_llm(
            b_profile_section
            + f"台灣即時空品快報（{datetime.now().strftime('%Y-%m-%d %H:%M')}）：\n"
            f"- 全國平均 AQI：{avg_aqi_pipe:.1f}\n"
            f"- 最高：{worst_pipe['city']} AQI {worst_pipe['aqi']:.0f}（{worst_pipe['level']}），PM2.5 {worst_pipe['PM2.5']} μg/m³\n"
            f"- 最低：{best_pipe['city']} AQI {best_pipe['aqi']:.0f}（{best_pipe['level']}），PM2.5 {best_pipe['PM2.5']} μg/m³\n"
            f"- 覆蓋城市：{len(snapshot)}\n\n"
            f"RAG 文獻可引用：\n"
            f"- WHO 2021：PM2.5 年均 ≤ 5 μg/m³，24h ≤ 15 μg/m³\n"
            f"- EPA NAAQS：PM2.5 24h ≤ 35 μg/m³\n"
            f"- Lancet 2023：高 PM2.5 下劇烈運動，肺部沉積量 ↑3-5x\n\n"
            f"請用 3 段繁體中文輸出：① 現況摘要 ② 健康建議 ③ 未來 6 小時研判。"
            f"每段 2-3 句，必須引用上方數值，不可編造其他城市或數字。"
            + (
                "若上方有「使用者個人健康檔案」，第 ② 段請額外針對此使用者個人"
                "（依其年齡 / BMI / 已診斷疾病）給 1-2 句量身建議。"
                if b_profile else ""
            ),
            max_tokens=4096,
        )
        if b_resp:
            st.session_state.llm_analysis = b_resp
            push_log("LLM", f"分析完成（{len(b_resp)} 字）", to="B")
        else:
            push_log("LLM", f"⚠ 失敗：{b_err}", to="B")
    else:
        push_log("B", "未填 LLM 金鑰，跳過風險分析（圖表仍會基於快照資料繪製）", to="SYS")
        time.sleep(0.3)

    push_log("B", "報告寫好了，轉交預警員生成健康建議", to="C")
    _refresh_log()
    progress.progress(0.75, text="分析師 · 完成")

    # ── 預警員 (C) ──────────────────────────────────────────────────────
    # 改版重點:
    #   ❶ 只在使用者「有填個人健康檔案 / 上傳病歷」時才呼叫 LLM。
    #      沒填 → 跳過 Agent C(省 token & API 配額),Section 07 改顯示
    #      CTA banner 引導使用者去填。
    #   ❷ 只為「所選城市」(沒點選 = 常駐城市)生成**一份詳細**建議
    #      (分 5 小節、250-450 字),而非 20 城市各 3 句 — 更深入、token 省 ~20 倍。
    #      prompt 由 _advisor_prompt_for_city() 統一組(SECTION 07 的「換城市重生」
    #      按鈕也用同一個),輸出由程式包成 <<<CITY:NAME>>> sentinel,下游相容。
    #   ❸ 注入 personal-scope RAG chunks,讓 LLM 引用使用者上傳的病歷檔。
    st.session_state.active_agent = "C"
    _status("C")
    push_log("B", "風險分析完成，把風險分級結果交給你發布預警", to="C")
    _refresh_log()
    time.sleep(0.25)

    c_profile = _personal_profile_block()
    if not c_profile:
        # ── 空白檔案路徑:略過 Agent C ─────────────────────────────────
        # 使用者沒填任何個人資料,給通用 5 群建議反而會誤導(「孕婦」對沒
        # 懷孕的人完全多餘)。改成提示使用者去填,UI 那邊會 render CTA banner。
        st.session_state.agent_c_advisories = ""
        push_log("C", "使用者未填個人健康檔案 — 略過個人化建議生成（UI 會顯示 CTA banner）", to="SYS")
        _refresh_log()
    elif has_llm:
        # 目標城市 = 跑 Pipeline 當下的「所選城市」(沒點選 = 封面填的常駐城市)
        _c_target = st.session_state.selected_city or st.session_state.get("user_city", "taipei")
        c_prompt, _c_row = _advisor_prompt_for_city(snapshot, _c_target)
        push_log("C", f"偵測到個人健康檔案 → 請 {prov_name} 為「{_c_row['city']}」生成詳細個人化建議", to="LLM")
        _refresh_log()
        # 與 SECTION 07「🔁 重生」按鈕共用同一個 system prompt,確保兩條路徑語氣一致
        c_resp, c_err = _agent_llm(c_prompt, max_tokens=3072, system=_ADVISOR_SYSTEM)
        if c_resp:
            # 程式包 sentinel(模型輸出純文字)→ parse / 匯出 / modal 全部相容
            st.session_state.agent_c_advisories = f"<<<CITY:{_c_row['city']}>>>\n{c_resp.strip()}\n"
            st.session_state.agent_c_city_id = str(_c_row["city_id"])
            push_log("LLM", f"「{_c_row['city']}」詳細個人化建議生成完成（{len(c_resp)} 字）", to="C")
        else:
            push_log("LLM", f"⚠ 失敗：{c_err}（UI 會顯示 fallback 提示）", to="C")
            st.session_state.agent_c_advisories = ""

    # ── SQLite TSDB write (本機時序快取) ─────────────────────────────────
    try:
        n_written = tsdb.write_snapshot(snapshot, st.session_state.data_mode)
        push_log("C", f"寫入本機 SQLite 時序快取（{n_written} 列 · {len(snapshot)} 城市）", to="DB")
    except Exception as e:
        push_log("C", f"⚠ SQLite 寫入失敗：{type(e).__name__}: {e}", to="DB")
    _refresh_log()
    time.sleep(0.15)

    # ── 匯出 JSON 供聊天平台 Agent Bot 拉取(本機範例:Hermes/Discord)──────
    # 拉取模型(取代舊的 webhook 推送):把這次 Pipeline 的結果寫成
    # agent_export/latest_aqi.json,bot 端 skill 讀它在聊天平台回答。
    try:
        _exp_path = _write_agent_export(snapshot)
        push_log("C", f"✓ 已匯出 {_exp_path.name}(Agent Bot 可拉取 · {len(snapshot)} 城市)", to="EXPORT")
    except Exception as e:
        push_log("C", f"⚠ JSON 匯出失敗:{type(e).__name__}: {e}", to="EXPORT")
    _refresh_log()
    time.sleep(0.15)

    push_log("SYS", "Pipeline 完成 ✓ 所有代理人下線", to="*")
    _refresh_log()
    time.sleep(0.2)

    # ── 24h history: EPA aqx_p_488 (official) + Open-Meteo CAMS (model) ──
    # Both fetched here so the "EPA vs CAMS" tabs in the heatmap section
    # always render. EPA hist may fail if api_key is missing — CAMS is the
    # always-on companion.
    # We pull CAMS past_days=7 (not 1) so the SQLite cache below has a full
    # week of hourly data to power the weekly-ranking and personal-trend
    # features. Display heatmap still filters to the last 24h.
    # 重要:`forecast_days=1` 把「今天」拉進來 — `past_days=N` 只回完整過去日,
    # 不含今天的任何小時。沒加 forecast_days=1 時,早上 10 點呼叫只會拿到「昨天
    # 23:00」當最新資料,落後 10+ 小時。filter `<= now` 砍掉預測段(now 之後的
    # 才是模型預測,now 之前的是 reanalysis 實測 + 數據同化)。
    cams_week = fetch_open_meteo_aq_batch(CITIES, past_days=7, forecast_days=1)
    cams_hist = None
    if cams_week is not None and not cams_week.empty:
        # 砍掉 now 之後的預測段,只留實際發生過的小時。沒這層 filter 會把
        # 預測資料當實測寫進 SQLite,影響後續的「本週 AQI」、「跟上週比」等統計。
        cams_week = cams_week[cams_week["timestamp"] <= pd.Timestamp(datetime.now())].copy()
    if cams_week is not None and not cams_week.empty:
        # Persist the full week into SQLite (UPSERT — re-runs don't duplicate)
        try:
            n_seed = tsdb.write_history_hourly(cams_week, source="cams_hourly")
            push_log("C", f"寫入歷史時序快取 · CAMS 過去 7 天（{n_seed} 列）", to="DB")
        except Exception as e:
            push_log("C", f"⚠ 歷史快取寫入失敗：{type(e).__name__}: {e}", to="DB")
        # Slice the last 24h for the heatmap display
        cutoff = pd.Timestamp(datetime.now()) - pd.Timedelta(hours=25)
        cams_hist = cams_week[cams_week["timestamp"] >= cutoff].copy()
    st.session_state.cams_ts_df = cams_hist
    _refresh_log()

    progress.progress(1.0, text="✓ Pipeline 完成")
    _status("X", done=True)
    st.session_state.pipeline_done = True
    st.session_state.active_agent  = None
    st.session_state.last_pipeline_run_at = datetime.now()
    time.sleep(0.3)
    st.rerun()


# =============================================================================
# 側邊欄 (Sidebar) — 設定區 + 資料源狀態
# =============================================================================
# Streamlit 預設右側展開的設定面板,包含:
#   - AgentAQI 品牌 logo
#   - 資料來源狀態(EPA / Open-Meteo)
#   - 自動更新 toggle(整點對齊 EPA)
#   - LLM 提供商選擇 + API key 輸入
#   - EPA API token 輸入
#   - RAG 知識庫 PDF 上傳區
#   - SQLite 時序快取狀態 + Agent Bot 匯出說明
# =============================================================================
with st.sidebar:
    st.markdown(
        "<div style='display:flex; align-items:center; gap:0.6rem; margin-bottom:1rem;'>"
        "<div style='font-size:1.8rem; filter: drop-shadow(0 0 12px #00d9ff)'>🤖</div>"
        "<div>"
        "<div style='font-size:1.05rem; font-weight:800; letter-spacing:-0.02em;'>AgentAQI</div>"
        "<div style='font-size:0.68rem; color:#8b95a8; font-family:JetBrains Mono; letter-spacing:0.18em;'>TAIWAN · MULTI-AGENT</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Data source info — always tries real EPA + Open-Meteo, auto-falls back
    st.markdown(
        "<div class='eyebrow'>資料來源</div>"
        "<div class='tiny muted' style='line-height:1.55;'>"
        "✓ EPA Open Data API (即時)<br>"
        "✓ Open-Meteo 氣象 (免金鑰)<br>"
        "⚙ 連線失敗時自動切換 mock"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # Auto-refresh: re-run pipeline every hour without user clicking "重新執行"
    st.markdown("<div class='eyebrow'>自動更新</div>", unsafe_allow_html=True)
    st.session_state.auto_refresh_enabled = st.toggle(
        "🔄 自動更新（頁面開著時，整點對齊 EPA）",
        value=st.session_state.get("auto_refresh_enabled", True),
        key="auto_refresh_toggle",
        help="瀏覽器分頁開著時，每跨入新的一個小時、過整點 10 分（等 EPA 發布新一輪數據）"
             "就自動重跑 Pipeline，與 EPA 每小時整點發布對齊。"
             "分頁關閉或電腦休眠時不會更新 — 重開頁面後按「重新執行 Pipeline」即可。",
    )

    st.markdown(" ")

    # In-app LLM provider (Pipeline + AI 助理都用這條路徑，毫秒級回應)
    st.markdown("<div class='eyebrow'>LLM 提供商</div>", unsafe_allow_html=True)
    prov_keys = list(LLM_PROVIDERS.keys())
    prov_idx  = prov_keys.index(st.session_state.llm_provider) if st.session_state.llm_provider in prov_keys else 0
    chosen_prov = st.selectbox(
        "LLM 提供商",
        options=prov_keys,
        format_func=lambda p: LLM_PROVIDERS[p]["name"],
        index=prov_idx,
        label_visibility="collapsed",
    )
    st.session_state.llm_provider = chosen_prov
    prov_cfg = LLM_PROVIDERS[chosen_prov]

    # type="default" + CSS mask via st.container(key=...) wrapper.
    # Chrome 不會把 default 欄位當密碼，所以不會跳「儲存密碼」popup。
    # 視覺上用 -webkit-text-security 顯示成黑點。
    with st.container(key="masked_llm_key"):
        st.session_state.llm_key = st.text_input(
            "API Key",
            value=st.session_state.llm_key,
            type="default",
            placeholder=prov_cfg["placeholder"],
        )
    # Model + Base URL are auto-derived from provider defaults (kept off the UI for simplicity)
    st.session_state.llm_model    = prov_cfg["default_model"]
    st.session_state.llm_base_url = prov_cfg.get("base_url", "")

    # Live status pill
    if st.session_state.llm_key.strip():
        st.markdown(
            f"<span class='pill green'><span class='dot'></span>"
            f"{escape(prov_cfg['name'])} · 金鑰已填</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span class='pill gray'><span class='dot'></span>未填金鑰 · 將跳過 LLM 評論</span>",
            unsafe_allow_html=True,
        )

    # ── 進階整合:Agent Bot(拉取模型)──────────────────────────────────
    # Pipeline 跑完會把結果匯出成 agent_export/latest_aqi.json,任何 agent bot
    # (以 Hermes 為範例)當聊天平台 bot 讀它回答(依個人檔案個人化)。
    # 不再用 webhook 推送 / cron 指令。設定與匯出狀態見 SECTION 10。
    st.markdown(
        "<div class='tiny muted' style='line-height:1.55; margin-top:0.6rem;'>"
        "🤖 Agent Bot 讀 <code>latest_aqi.json</code> 在聊天平台回答空品 — 詳見 SECTION 10 與 README『Agent Bot 整合』段。"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # EPA Open Data Token (環境部 data.moenv.gov.tw — v2 endpoint requires api_key)
    st.markdown("<div class='eyebrow'>EPA Open Data</div>", unsafe_allow_html=True)
    with st.container(key="masked_epa_key"):
        st.session_state.epa_key = st.text_input(
            "EPA Token",
            value=st.session_state.epa_key,
            type="default",
            placeholder="貼上你的 api_key（必填）",
            help="環境部 v2 API 必須有 token 才能取得資料。",
        )

    if st.button("🔌 測試 EPA Token", use_container_width=True, key="epa_test_btn"):
        import requests as _req
        token = (st.session_state.epa_key or "").strip()
        token_len = len(token)
        try:
            params = {"limit": 1, "format": "JSON"}
            if token:
                params["api_key"] = token
            r = _req.get(
                "https://data.moenv.gov.tw/api/v2/aqx_p_432",
                params=params, timeout=15,
            )
            ct = r.headers.get("Content-Type", "")
            # MOENV returns HTTP 200 even for auth errors; sniff body
            if "json" in ct.lower():
                try:
                    body = r.json()
                    # MOENV v2 has been seen returning:
                    #   {"records": [...], "total": N}    (older)
                    #   [{...}, {...}]                    (newer / array)
                    #   {"data": [...]}                   (some endpoints)
                    #   {"result": {"records": [...]}}    (wrapped)
                    records = None
                    if isinstance(body, list):
                        records = body
                    elif isinstance(body, dict):
                        records = (body.get("records")
                                   or body.get("data")
                                   or body.get("rows")
                                   or (body.get("result", {}) or {}).get("records"))
                    if isinstance(records, list) and records:
                        sample = records[0] if isinstance(records[0], dict) else {}
                        total  = (body.get("total") if isinstance(body, dict) else None) or len(records)
                        st.session_state["epa_test_result"] = (
                            "ok",
                            f"✓ Token 有效 · 取得 {total} 測站 · 例：{sample.get('SiteName', sample.get('sitename', '?'))} AQI {sample.get('AQI', sample.get('aqi', '?'))}",
                        )
                    else:
                        # JSON parsed but unknown shape — show top-level keys + preview
                        if isinstance(body, dict):
                            shape = f"dict keys={list(body.keys())[:8]}"
                        elif isinstance(body, list):
                            shape = f"list len={len(body)}"
                        else:
                            shape = type(body).__name__
                        preview = json.dumps(body, ensure_ascii=False)[:200] if body else "(empty)"
                        st.session_state["epa_test_result"] = (
                            "err", f"❌ JSON 解出但找不到 records · 結構：{shape} · 內容：{preview}"
                        )
                except Exception as e:
                    preview = (r.text or "")[:200]
                    st.session_state["epa_test_result"] = (
                        "err", f"❌ JSON parse 失敗（{type(e).__name__}）· 前 200 字：{preview}"
                    )
            else:
                # Plain text error from MOENV
                text = (r.text or "").strip()[:200]
                hint = ""
                if "不存在" in text or "到期" in text:
                    hint = "  → token 字串錯誤或已過期，到平臺『個人專區』複製完整版"
                elif token_len == 0:
                    hint = "  → 還沒填 token"
                elif token_len < 30:
                    hint = f"  → token 長度 {token_len} 字，看起來太短（標準格式約 36 字、UUID-like）"
                st.session_state["epa_test_result"] = (
                    "err", f"❌ HTTP {r.status_code} · MOENV 回應：「{text}」{hint}"
                )
        except _req.exceptions.SSLError as e:
            st.session_state["epa_test_result"] = (
                "err",
                f"❌ SSL 憑證驗證失敗 — 可能是 OpenSSL 3.5+ 嚴格模式對環境部憑證的相容性問題。"
                f"請確認已安裝 truststore（pip install truststore）。原始錯誤：{str(e)[:160]}"
            )
        except _req.exceptions.ConnectionError as e:
            # ConnectionError 在 requests 裡是個大籠子 — 真正的 DNS 失敗、TCP 拒絕、
            # SSL handshake 失敗、proxy 設錯、防毒軟體擋 SNI 全部會掉進來。
            # 把原始訊息露出來,使用者才能對症下藥(過去只顯示「DNS / 防火牆」沒幫助)。
            detail = str(e)[:240] if str(e) else "(無錯誤訊息)"
            hint = ""
            low = detail.lower()
            if "max retries" in low and "ssl" in low:
                hint = "  → 看起來是 SSL 問題,執行 `pip install truststore` 後重啟 Streamlit"
            elif "getaddrinfo" in low or "name or service not known" in low or "name resolution" in low:
                hint = "  → DNS 解析失敗,檢查網路 / VPN / Hosts 檔"
            elif "refused" in low or "actively refused" in low:
                hint = "  → TCP 連線被拒,可能是防火牆 / 防毒擋掉"
            elif "proxy" in low:
                hint = "  → Python 抓到 proxy 設定,檢查 HTTP_PROXY / HTTPS_PROXY 環境變數"
            elif "remote end closed" in low or "connection aborted" in low:
                hint = "  → 連到一半被切斷,通常是暫時性,稍後再試"
            st.session_state["epa_test_result"] = (
                "err",
                f"❌ 連線失敗 — {detail}{hint}"
            )
        except _req.exceptions.Timeout:
            st.session_state["epa_test_result"] = (
                "err",
                "❌ 連線逾時(>15s) — data.moenv.gov.tw 可能負載高,稍等再試"
            )
        except Exception as e:
            st.session_state["epa_test_result"] = ("err", f"❌ {type(e).__name__}: {e}")

    test_result = st.session_state.get("epa_test_result")
    if test_result:
        kind, msg = test_result
        pill_class = "green" if kind == "ok" else "red"
        # Use plain div instead of pill so longer error text wraps nicely
        bg = "rgba(0, 230, 118, 0.10)" if kind == "ok" else "rgba(255, 71, 87, 0.10)"
        bd = "#00e676" if kind == "ok" else "#ff4757"
        st.markdown(
            f"<div style='padding:0.55rem 0.75rem; background:{bg}; border-left:3px solid {bd}; "
            f"border-radius:0 8px 8px 0; font-size:0.78rem; line-height:1.5; color:#e8eef7; margin-top:0.4rem; word-break:break-all;'>"
            f"{escape(msg)}"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='tiny muted' style='line-height:1.55; margin-top:0.3rem;'>"
        "📘 申請：<a href='https://data.moenv.gov.tw/' target='_blank' style='color:#00d9ff;'>環境部資料開放平臺</a>"
        " → 註冊 → 個人專區 → API 金鑰"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # ── 本機時序快取狀態 ─────────────────────────────────────────────────
    _tsdb_stats = tsdb.stats()
    last_w = _tsdb_stats["last_write"] or "—"
    if isinstance(last_w, str) and "T" in last_w:
        last_w = last_w.replace("T", " ")[:19]
    st.markdown("<div class='eyebrow'>本機時序快取</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='padding:0.5rem 0.7rem; background:rgba(78,236,255,0.06); "
        f"border-left:3px solid #4eecff; border-radius:0 8px 8px 0; "
        f"font-size:0.75rem; line-height:1.55; color:#c0c8d8;'>"
        f"<b style='color:#4eecff; font-family:JetBrains Mono;'>{_tsdb_stats['rows']:,}</b> 筆 · "
        f"{_tsdb_stats['runs']} 次 pipeline 執行 · "
        f"{_tsdb_stats['cities']} 城市<br>"
        f"<span class='tiny muted'>最後寫入：{last_w}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # Pipeline button — only shown after first run (initial launch is on the cover page)
    run_clicked = False
    if st.session_state.pipeline_done:
        st.markdown("<div class='eyebrow'>Pipeline</div>", unsafe_allow_html=True)
        run_clicked = st.button(
            "↻  重新執行 Pipeline",
            type="primary", use_container_width=True,
        )
        _lr = st.session_state.get("last_pipeline_run_at")
        if _lr:
            st.markdown(
                f"<div class='tiny muted'>上次執行：{_lr.strftime('%m/%d %H:%M')}</div>",
                unsafe_allow_html=True,
            )

    st.markdown(" ")

    # ── RAG knowledge base (real PDF / TXT / MD extraction) ────────────────
    st.markdown("<div class='eyebrow'>RAG 知識庫</div>", unsafe_allow_html=True)
    _seed_rag_chunks()  # ensures the WHO/EPA/Lancet/MOENV starter chunks exist
    uploaded = st.file_uploader(
        "拖曳 PDF / TXT / MD 至此（會解析內容，加進 RAG 檢索池）",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="rag_uploader",
    )
    if uploaded:
        seen_files = {f["name"] for f in st.session_state.rag_files}
        for f in uploaded:
            if f.name in seen_files:
                continue
            n_chunks = _ingest_uploaded_file(f)
            st.session_state.rag_files.append({
                "name":     f.name,
                "size":     f"{f.size / 1024:.0f} KB",
                "added":    datetime.now().strftime("%m/%d %H:%M"),
                "n_chunks": n_chunks,
            })
            seen_files.add(f.name)
        st.rerun()

    rag_text = st.text_area(
        "或貼上文字片段",
        placeholder="貼上文獻摘要、研究結論...",
        height=68,
    )
    if st.button("✚ 加入 RAG", use_container_width=True) and rag_text.strip():
        snippet_id = sum(1 for c in st.session_state.rag_chunks if c["source"].startswith("snippet_"))
        st.session_state.rag_chunks.append({
            "source": f"snippet_{snippet_id:03d}.txt",
            "text":   rag_text.strip(),
            "page":   1,
        })
        st.session_state.rag_files.append({
            "name":     f"snippet_{snippet_id:03d}.txt",
            "size":     f"{len(rag_text)} chars",
            "added":    datetime.now().strftime("%m/%d %H:%M"),
            "n_chunks": 1,
        })
        st.rerun()

    # File list (uploaded files + manual snippets)
    files_html = "".join(
        f"<div class='comm-row' style='font-size:0.7rem;'>"
        f"<span style='color:#00d9ff;'>▸</span> "
        f"<span style='color:#e8eef7;'>{escape(d['name'][:30])}</span>"
        f"<div class='tiny muted' style='margin-left:1rem;'>"
        f"{d['size']} · {d.get('n_chunks', '?')} chunks · {d['added']}"
        f"</div></div>"
        for d in st.session_state.rag_files
    )
    if files_html:
        st.markdown(
            f"<div class='comm-log' style='max-height:170px; font-size:0.7rem;'>{files_html}</div>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"📚 {len(st.session_state.rag_chunks)} 段可檢索內容 · "
        f"{len(st.session_state.rag_files)} 個檔案"
    )

    st.markdown("---")

    # Section nav
    st.markdown("<div class='eyebrow'>章節導覽</div>", unsafe_allow_html=True)
    sections = [
        ("agents",  "🤖 代理人劇場"),
        ("dash",    "📊 主儀表板"),
        ("trend",   "📈 24 小時趨勢"),
        ("pollute", "🧪 污染物剖析"),
        ("env",     "🌬 環境關聯"),
        ("source",  "📡 資料來源對比"),
        ("health",  "🏥 健康預警"),
        ("perso",   "👤 個人化推薦"),
    ]
    for sid, name in sections:
        st.markdown(
            f"<a href='#{sid}' style='display:block; padding:0.45rem 0.7rem; "
            f"color:#c0c8d8; text-decoration:none; border-left:2px solid transparent; "
            f"font-size:0.85rem; transition:all 0.2s;' "
            f"onmouseover='this.style.borderColor=\"#00d9ff\"; this.style.color=\"#00d9ff\"; this.style.background=\"rgba(0,217,255,0.08)\"' "
            f"onmouseout='this.style.borderColor=\"transparent\"; this.style.color=\"#c0c8d8\"; this.style.background=\"transparent\"'>"
            f"{name}</a>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    # NOTE: 「聚焦城市」與「時間範圍」UI 已移除。城市聚焦改由「主儀表板 → 城市排行」
    # 圖點擊事件設定（session_state.selected_city 仍保留供圖表 highlight 用）；
    # 時間範圍改用儀表板上方的時間軸 scrubber。
    st.markdown(
        "<div class='tiny muted' style='text-align:center;'>"
        "Built with 🤖 · Streamlit + Plotly<br>"
        "資料來源：環境部 / LASS-net / Open-Meteo"
        "</div>",
        unsafe_allow_html=True,
    )



ANTI_HALLUCINATION_SYSTEM = (
    "你是 AgentAQI 的 AI 助理。你必須嚴格遵守以下規則：\n"
    "1. 只能基於使用者訊息中提供的『資料快照』和『RAG 文獻庫』作答，禁止編造資料中沒有的數字、城市、等級或事件。\n"
    "2. 若使用者問題的答案不在資料中，必須明確回覆：『目前資料中沒有這項資訊』，並建議使用者調整提問或啟動 Pipeline。\n"
    "3. 回答時直接引用具體數值（例如『台北市 AQI 為 42』），不使用模糊詞如『大概』、『可能』。\n"
    "4. 若引用 WHO/EPA/Lancet 結論，只引用 RAG 文獻庫中已列出的條目，標明來源。\n"
    "5. 一律使用繁體中文，回覆長度不設限——該講完的就講完整，但不要灌水或重複。\n"
    "6. 不要回答與台灣空氣品質、健康建議無關的話題。"
)


# ─── 個人化健康檔案 helpers(RAG 個人化升級)──────────────────────────────
# 兩個 helper 處理「個人健康檔案」(封面步驟①)的衍生資料:
#   - _calc_bmi:由身高體重計算 BMI 與中文分類(用於 UI 即時顯示 + 注入 LLM prompt)
#   - _personal_profile_block:把全部個人欄位拼成 LLM prompt 注入段落
# 若使用者沒填任何欄位(零回歸測試),_personal_profile_block 回空字串,
# 所有 prompt 的內容就會與升級前完全一致。
# ─────────────────────────────────────────────────────────────────────────────

def _calc_bmi(height_cm: float, weight_kg: float) -> tuple[float, str]:
    """由身高 cm 與體重 kg 計算 BMI,並回傳 (BMI 數值, 中文分類)。

    分類依 WHO 標準(亞洲略嚴於歐美但本專案用 WHO 通用版以求一致):
      < 18.5     過輕
      18.5-23.9  正常
      24-26.9    過重
      27-29.9    輕度肥胖
      30-34.9    中度肥胖
      ≥ 35       重度肥胖

    Returns
    -------
    tuple[float, str]
        (bmi, category) — height<=0 時回 (0.0, "—")
    """
    if height_cm <= 0:
        return 0.0, "—"
    h_m = height_cm / 100.0
    bmi = weight_kg / (h_m * h_m)
    if bmi < 18.5:   cat = "過輕"
    elif bmi < 24:   cat = "正常"
    elif bmi < 27:   cat = "過重"
    elif bmi < 30:   cat = "輕度肥胖"
    elif bmi < 35:   cat = "中度肥胖"
    else:            cat = "重度肥胖"
    return bmi, cat


def _personal_profile_block() -> str:
    """組合給 LLM 的「使用者個人健康檔案」段落,供 prompt 注入用。

    用途:在 _build_chat_context、Pipeline 分析師(B)、預警員(C)的 prompt 中
    各插入這段,LLM 就能看到 年齡 / 性別 / BMI / ICD-10 診斷 / 病歷重點,
    給出比通用建議更具體的個人化回答。

    為什麼空檔案回空字串?
      使用者沒填(初次造訪、未展開 expander)時,我們不想干擾 LLM —
      回空字串表示「prompt 注入完全不發生」,LLM 行為與升級前 100% 一致。
      只有當使用者主動填寫至少一個欄位(年齡>0 / 有診斷 / 有病歷)才注入。

    Returns
    -------
    str
        多行字串(含尾端 \\n),或空字串(""):當使用者完全沒填時。
    """
    age   = st.session_state.get("user_age", 0) or 0
    diags = st.session_state.get("user_diagnoses", []) or []
    hist  = (st.session_state.get("user_med_history") or "").strip()
    # 三個關鍵欄位全空 → 不注入(零回歸)
    if not (age or diags or hist):
        return ""
    bmi, bmi_cat = _calc_bmi(
        st.session_state.get("user_height_cm", 0) or 0,
        st.session_state.get("user_weight_kg", 0) or 0,
    )
    diag_text = "、".join(
        f"{d['label']}({d['code']})"
        for d in USER_ICD10_OPTIONS if d["code"] in diags
    ) or "無"
    sex_label = {
        "female":      "女",
        "male":        "男",
        "other":       "其他",
        "prefer_not":  "未提供",
    }.get(st.session_state.get("user_sex", "prefer_not"), "未提供")
    age_txt = f"{age} 歲" if age else "未提供"
    # 閾值放在「閘門之後」才注入:它有預設值 100(永遠非空),若參與上面的
    # 三欄位閘門判斷,會讓「完全沒填」的使用者也被視為已填,破壞零回歸保證。
    thr = int(st.session_state.get("user_aqi_threshold", 100))
    return (
        "=== 使用者個人健康檔案（請在回答中明確參考這些因素）===\n"
        f"年齡：{age_txt} / 性別：{sex_label} / BMI：{bmi:.1f}（{bmi_cat}）\n"
        f"已診斷疾病：{diag_text}\n"
        f"病歷重點：{hist or '（未填）'}\n"
        f"自設 AQI 預警閾值：{thr}（使用者認為「超過就該注意」的個人標準，"
        "給建議時請以此為門檻，而非公定 100）\n"
        "請在建議中明確提及這些因素如何影響此使用者的個人風險（例如年齡>65、有 COPD、BMI 過重等），"
        "不要僅給通用建議。\n"
    )


def _render_persona_step1() -> None:
    """封面「步驟 ①」個人健康檔案輸入(在啟動 Pipeline 之前)。

    為什麼放在 Pipeline 之前:分析師(B)/ 預警員(C)的 LLM prompt 是在 run_pipeline()
    期間用 _personal_profile_block() 組的。把 persona 填在「跑之前」,第一次跑就吃得到
    →根治舊版「填完要重跑一次」的問題。填好的 persona 也會隨 Pipeline 匯出進
    agent_export/latest_aqi.json,供聊天平台 Agent Bot 個人化回答。

    所有欄位沿用既有 session_state mirror(user_*)+ widget key(user_*_input /
    *_select),SECTION 08 改成只讀結果,不再有同名 widget,故無 key 衝突。
    """
    st.markdown(
        "<div style='text-align:center; margin-top:0.2rem;'>"
        "<div class='eyebrow' style='display:inline-block;'>"
        "步驟 ① 個人健康檔案（選填 · 填了分析師 / 預警員 / Agent Bot 才會個人化）</div></div>",
        unsafe_allow_html=True,
    )
    _pc = st.columns([1, 2, 1])[1]   # 置中欄,避免表單佔滿整個封面寬度
    with _pc:
        with st.expander(
            "✍️ 展開填寫 / 編輯個人健康檔案",
            expanded=False,
        ):
            user_city = st.selectbox(
                "📍 你常駐城市",
                options=[c["id"] for c in CITIES],
                format_func=lambda cid: CITY_BY_ID[cid]["name"],
                index=next(i for i, c in enumerate(CITIES) if c["id"] == st.session_state.user_city),
                key="user_city_select",
            )
            st.session_state.user_city = user_city

            # ── 個人化錨點:儀表板各區的「預設城市」跟著你的城市走 ──────────
            # 第一次進來、或你换了常駐城市 → 把趨勢圖 / 雷達圖的預設清單重新
            # 錨定成「你的城市排第一」,並 pop 掉 keyed widget 的舊狀態讓新預設
            # 生效。之後你在圖表裡自由增減城市,不會再被強制改回。
            if st.session_state.get("_anchor_city") != user_city:
                st.session_state["_anchor_city"] = user_city
                # 趨勢圖預設「只放你的城市」一條線(乾淨聚焦;要比較再自己多選)
                st.session_state.trend_cities = [user_city]
                st.session_state.radar_cities = ([user_city] + [
                    c for c in st.session_state.radar_cities if c != user_city
                ])[:4]
                st.session_state.pop("trend_select", None)
                st.session_state.pop("radar_select", None)

            # 不再用「五大敏感族群」分桶 —— 改成你個人的 AQI 預警閾值(個人化)。
            # 健康狀況改由下方「已診斷疾病(ICD-10)」+ 病歷重點 + 年齡 表達。
            st.session_state.user_aqi_threshold = st.number_input(
                "⚠ 我的 AQI 預警閾值",
                min_value=20, max_value=300, step=10,
                value=int(st.session_state.get("user_aqi_threshold", 100)),
                key="user_aqi_threshold_input",
                help="你個人覺得「超過就該注意」的 AQI;用來算下方『個人化健康指數』與主畫面預警橫幅。"
                     "一般成人約 100,呼吸道 / 心血管敏感可設低些(如 60)。",
            )

            st.markdown("<div style='height:0.4rem;'></div>", unsafe_allow_html=True)
            st.info(
                "🔒 **隱私說明** — 個人健康檔案只存在你本機 session。跑 Pipeline 時會:"
                "(a) 作為 prompt context 送到你**自己設定**的 LLM 雲端 API(Anthropic / Gemini / "
                "OpenAI / MiniMax)做個人化分析;(b) 寫進本機 `agent_export/latest_aqi.json`,供你"
                "**自架的 Agent Bot(聊天平台)** 讀取回答。**不會傳給專案作者或任何第三方**;想移除按下方「🗑 清除」。"
            )

            # 年齡 + 性別
            col_age, col_sex = st.columns(2)
            with col_age:
                st.session_state.user_age = st.number_input(
                    "👤 年齡",
                    min_value=0, max_value=120, step=1,
                    value=int(st.session_state.user_age),
                    key="user_age_input",
                    help="0 = 不提供(分析師 / 預警員不會注入年齡);填實際年齡(如 72)才會據此個人化",
                )
            with col_sex:
                _sex_opts = ["prefer_not", "female", "male", "other"]
                _sex_labels = {"prefer_not": "不提供", "female": "女", "male": "男", "other": "其他"}
                st.session_state.user_sex = st.selectbox(
                    "⚧ 性別",
                    options=_sex_opts,
                    index=_sex_opts.index(st.session_state.user_sex) if st.session_state.user_sex in _sex_opts else 0,
                    format_func=lambda s: _sex_labels.get(s, s),
                    key="user_sex_input",
                )

            # 身高 + 體重 + BMI
            col_h, col_w = st.columns(2)
            with col_h:
                st.session_state.user_height_cm = st.number_input(
                    "📏 身高 (cm)",
                    min_value=80.0, max_value=230.0, step=0.5,
                    value=float(st.session_state.user_height_cm),
                    key="user_height_input",
                )
            with col_w:
                st.session_state.user_weight_kg = st.number_input(
                    "⚖ 體重 (kg)",
                    min_value=20.0, max_value=200.0, step=0.5,
                    value=float(st.session_state.user_weight_kg),
                    key="user_weight_input",
                )
            _bmi, _bmi_cat = _calc_bmi(
                st.session_state.user_height_cm, st.session_state.user_weight_kg
            )
            st.caption(f"BMI：**{_bmi:.1f}**（{_bmi_cat}）")

            # ICD-10
            st.session_state.user_diagnoses = st.multiselect(
                "🏥 已診斷疾病（ICD-10，可複選）",
                options=[d["code"] for d in USER_ICD10_OPTIONS],
                default=st.session_state.user_diagnoses,
                format_func=lambda code: next(
                    f"{d['icon']} {d['label']} （{d['code']}）"
                    for d in USER_ICD10_OPTIONS if d["code"] == code
                ),
                key="user_diagnoses_input",
                help="勾選你已被醫師確診的疾病。這會讓 AI 助理 / 預警員 / Agent Bot 針對你的疾病給專屬建議。",
            )

            # 病歷重點
            st.session_state.user_med_history = st.text_area(
                "📝 病歷重點（自填，建議 100-300 字）",
                value=st.session_state.user_med_history,
                height=120,
                placeholder=(
                    "例：2020 確診 COPD GOLD II 級，FEV1 65%；2022 心臟支架手術；"
                    "目前服用 Spiriva + Aspirin。空氣品質差時偶有咳嗽與胸悶。"
                ),
                key="user_med_history_input",
            )

            # 個人病歷檔上傳
            _uploaded_meds = st.file_uploader(
                "📎 上傳個人病歷文件（可選，PDF / TXT / MD）",
                type=["pdf", "txt", "md"],
                accept_multiple_files=True,
                key="user_med_files_uploader",
                help=(
                    "上傳的內容會被切成段落加入 RAG 知識庫，並標記為「個人病歷」"
                    "（在檢索時享有 1.4× 加權，AI 助理 / Pipeline 會優先參考）。"
                ),
            )
            if _uploaded_meds:
                _already = {d["name"] for d in st.session_state.user_med_files}
                for _mf in _uploaded_meds:
                    if _mf.name in _already:
                        continue
                    _n = _ingest_personal_medical_file(_mf)
                    if _n > 0:
                        st.success(f"✓ 已加入「{_mf.name}」({_n} 段) 為個人病歷 chunks")
            if st.session_state.user_med_files:
                st.caption(
                    "已上傳病歷：" + "、".join(
                        f"`{d['name']}`({d['n_chunks']} 段)"
                        for d in st.session_state.user_med_files
                    )
                )

            # 清除按鈕
            if st.button(
                "🗑 清除個人健康資料",
                help="把上方所有欄位回預設,並從 RAG 池移除所有 scope=personal 的 chunks",
                key="user_clear_health_btn",
            ):
                st.session_state.user_age         = 0   # 0 = 未提供
                st.session_state.user_sex         = "prefer_not"
                st.session_state.user_height_cm   = 165.0
                st.session_state.user_weight_kg   = 60.0
                st.session_state.user_diagnoses   = []
                st.session_state.user_med_history = ""
                st.session_state.user_med_files   = []
                st.session_state.user_aqi_threshold = 100   # 回一般成人預設
                st.session_state.rag_chunks = [
                    c for c in st.session_state.rag_chunks
                    if c.get("scope") != "personal"
                ]
                for _wk in (
                    "user_age_input", "user_sex_input", "user_height_input",
                    "user_weight_input", "user_diagnoses_input", "user_med_history_input",
                    "user_aqi_threshold_input",
                ):
                    st.session_state.pop(_wk, None)
                st.success("✓ 已清除個人健康資料與 personal RAG chunks")
                st.rerun()


def _build_chat_context() -> str:
    """組裝給 AI 助理 LLM 的「結構化事實上下文」。

    將 snapshot 中所有城市的當下數據、Pipeline 分析師 / 預警員的輸出,
    全部以條列方式列出。LLM 在回答使用者問題時必須引用這些數值,
    不可編造其他城市或數字(由 ANTI_HALLUCINATION_SYSTEM prompt 強制)。

    為什麼這樣設計?
      - 與其讓 LLM 各家自己「猜」AQI 數值,不如把真實數據塞進 prompt
      - 中文 + 結構化 prefix 「=== 資料快照 ===」讓 LLM 易解析
      - 同時把 mode tag (LIVE / MOCK) 帶進來,LLM 可以據此選擇措辭
        (例如 MOCK 時提醒使用者「目前顯示模擬資料」)
    """
    snap = st.session_state.snapshot
    if snap is None:
        return "（目前尚未啟動 Pipeline，無即時資料可供參考。）"

    rows = []
    for _, r in snap.iterrows():
        rows.append(
            f"  - {r['city']}（{r['region']}）：AQI {r['aqi']:.0f}（{r['level']}）, "
            f"PM2.5 {r['PM2.5']} μg/m³, PM10 {r['PM10']}, O3 {r['O3']} ppb, "
            f"NO2 {r['NO2']}, SO2 {r['SO2']}, 風險分數 {r['risk']:.0f}/100"
        )
    avg   = snap['aqi'].mean()
    worst = snap.sort_values('aqi', ascending=False).iloc[0]
    best  = snap.sort_values('aqi').iloc[0]
    mode  = "LIVE 即時 EPA API" if st.session_state.data_mode == "real" else "MOCK 模擬資料"
    # 個人化檔案注入(若使用者已填則回非空字串,否則為 "" 不影響 prompt)
    profile = _personal_profile_block()
    profile_section = (profile + "\n") if profile else ""
    return (
        f"=== 資料快照（{datetime.now().strftime('%Y-%m-%d %H:%M')}） ===\n"
        f"資料來源：{mode}\n"
        f"全國平均 AQI：{avg:.1f}\n"
        f"最高城市：{worst['city']} AQI {worst['aqi']:.0f}（{worst['level']}）\n"
        f"最低城市：{best['city']} AQI {best['aqi']:.0f}（{best['level']}）\n"
        f"覆蓋城市數：{len(snap)}\n\n"
        f"各城市詳細數據：\n" + "\n".join(rows) + "\n\n"
        + profile_section
        + f"=== 各 agent 分析摘要 ===\n"
        f"分析師（風險分析）：{st.session_state.get('llm_analysis', '（未生成）')}\n"
        f"預警員（健康預警）：{st.session_state.get('agent_c_advisories', '（未生成）')}\n"
    )


def _render_chat_panel() -> None:
    """渲染右下角浮動 AI 助理對話面板(LINE 風格 UI)。

    呼叫者(`if st.session_state.chat_expanded:` 區塊)已先渲染聯絡欄
    (機器人頭像 + 名稱 + 「在線」狀態)與右上角關閉按鈕。
    本函式接著按以下順序渲染面板內容:

      1. **對話歷史** — 用 `st.empty()` 預留位置,LLM 思考時可顯示「打字中」氣泡
      2. **使用者輸入框** — `st.chat_input`,Streamlit 自動釘在容器最底
      3. 送出後:
         - 寫入 user message → 歷史
         - 用 retrieve_rag_chunks 找相關文獻
         - 組合 prompt(context + RAG + 使用者問題)
         - 呼叫 call_llm_api
         - 寫入 assistant message + refs → 歷史
         - `st.rerun()` 釋放 chat_input widget,讓使用者可連續輸入(Fix-3a)

    CSS 部分(styles.py):
      - `.st-key-floating_chat`:面板 fixed 在右下角,640px 高度
      - `.st-key-chat_history`:flex column + justify-content: flex-end,
        確保歡迎訊息與短對話貼底(Fix-3b)
      - chat_input 有 `order: 99` 強制永遠在最底
    """
    pipeline_ready = st.session_state.pipeline_done and st.session_state.snapshot is not None
    has_llm        = bool(st.session_state.llm_key.strip())

    # Scoped scroll container: history scrolls independently, so the chat_input
    # below stays pinned to the panel's bottom edge no matter how far the user
    # scrolls up the conversation.
    with st.container(key="chat_history"):
        history_ph = st.empty()

    def _bubble_html(msg: dict) -> str:
        """Build one chat row + (for bot messages with refs) a collapsible
        references block immediately below it.

        Layout mirrors real LINE:
          - Bot:   [avatar] [bubble] [time]   (left-aligned, time on right)
          - User:  [time] [bubble]            (right-aligned, no own-avatar)
        For bot replies that cite RAG sources, we render a native `<details>`
        element under the bubble — collapsed by default, expandable per
        message. This is HTML (not st.expander) so we can keep the entire
        history flow as a single markdown blob, allowing mid-LLM-call repaints.
        """
        text_html = escape(msg["content"]).replace("\n", "<br>")
        time_str  = escape(msg.get("time", ""))

        if msg["role"] == "assistant":
            bubble_row = (
                "<div class='line-row line-row-bot'>"
                "<div class='line-avatar line-avatar-bot'>🤖</div>"
                f"<div class='line-bubble line-bubble-bot'>{text_html}</div>"
                f"<div class='line-bubble-time'>{time_str}</div>"
                "</div>"
            )
            refs = msg.get("refs") or []
            if refs:
                refs_inner = "".join(
                    f"<div class='ref-item'>"
                    f"<div class='ref-source'>{escape(r['source'])}</div>"
                    f"<div class='ref-quote'>{escape(r['quote'])}</div>"
                    f"</div>"
                    for r in refs
                )
                refs_row = (
                    "<div class='line-refs-row'>"
                    "<details class='line-bubble-refs'>"
                    f"<summary>📚 引用 RAG 內的文獻（{len(refs)} 篇）</summary>"
                    f"<div class='ref-list'>{refs_inner}</div>"
                    "</details>"
                    "</div>"
                )
                return bubble_row + refs_row
            return bubble_row

        # User
        return (
            "<div class='line-row line-row-me'>"
            f"<div class='line-bubble-time'>{time_str}</div>"
            f"<div class='line-bubble line-bubble-me'>{text_html}</div>"
            "</div>"
        )

    TYPING_HTML = (
        "<div class='line-row line-row-bot'>"
        "<div class='line-avatar line-avatar-bot'>🤖</div>"
        "<div class='line-bubble line-bubble-bot line-bubble-typing'>"
        "<span class='line-typing-dots'><span></span><span></span><span></span></span>"
        "</div>"
        "</div>"
    )

    def _draw(show_typing: bool) -> None:
        # Empty state — 用「助理主動打招呼」的氣泡呈現(比一行置中灰字更像真人/LINE)。
        # 依 Pipeline 是否就緒給不同開場白:就緒→邀請發問;未就緒→引導先啟動。
        if not st.session_state.chat_history and not show_typing:
            today_label = datetime.now().strftime("%Y/%m/%d")
            greeting = (
                "哈囉 👋 我是 AgentAQI 小助理。\n"
                "可以問我各城市的即時空品、PM2.5，或今天適不適合出門運動～"
            ) if pipeline_ready else (
                "哈囉 👋 我是 AgentAQI 小助理。\n"
                "先點頁面上方的「啟動 Pipeline」抓即時資料,我就能開始幫你看空氣品質囉。"
            )
            greeting_html = escape(greeting).replace("\n", "<br>")
            history_ph.markdown(
                "<div class='line-chat-stream'>"
                f"<div class='line-date-separator'><span>{today_label}</span></div>"
                "<div class='line-row line-row-bot'>"
                "<div class='line-avatar line-avatar-bot'>🤖</div>"
                f"<div class='line-bubble line-bubble-bot'>{greeting_html}</div>"
                "</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        # Date separator at top of conversation (LINE-style centered chip)
        today_label = datetime.now().strftime("%Y/%m/%d")
        parts = [
            f"<div class='line-date-separator'><span>{today_label}</span></div>"
        ]
        parts.extend(_bubble_html(m) for m in st.session_state.chat_history[-20:])
        if show_typing:
            parts.append(TYPING_HTML)
        history_ph.markdown(
            "<div class='line-chat-stream'>" + "".join(parts) + "</div>",
            unsafe_allow_html=True,
        )

    # Capture user input (st.chat_input pins itself to the bottom of the panel
    # in DOM regardless of where we call it).
    placeholder = "問我空氣品質的問題..." if pipeline_ready else "請先啟動 Pipeline..."
    user_msg = st.chat_input(placeholder, key="floating_chat_input")

    if user_msg:
        st.session_state.chat_history.append({
            "role":    "user",
            "content": user_msg,
            "time":    datetime.now().strftime("%H:%M"),
        })

        if not pipeline_ready:
            st.session_state.chat_history.append({
                "role":    "assistant",
                "content": "Pipeline 尚未啟動，目前沒有資料可供分析。請先點頁面上方的「啟動 Pipeline」。",
                "refs":    [],
                "time":    datetime.now().strftime("%H:%M"),
            })
        else:
            # Show the typing bubble immediately, then block on the LLM call.
            _draw(show_typing=True)

            # Dynamic RAG retrieval — pull only the chunks actually relevant
            # to this user question (starter snippets + any uploaded PDF
            # contents). The same chunks become the message's `refs` so the
            # user sees what the LLM was given.
            _seed_rag_chunks()
            picked_chunks = retrieve_rag_chunks(user_msg, top_k=5)
            picked_refs = [
                {"source": c["source"], "quote": c["text"]} for c in picked_chunks
            ]

            rag_block = "=== RAG 檢索結果（僅可引用以下條目） ===\n" + "\n".join(
                f"  [{c['source']}] {c['text']}" for c in picked_chunks
            )
            full_prompt = (
                _build_chat_context()
                + "\n\n" + ANTI_HALLUCINATION_SYSTEM
                + "\n\n" + rag_block
                + f"\n\n=== 使用者問題 ===\n{user_msg}\n\n"
                "請嚴格依據上方資料作答。如資料不足，明確說明無法回答。"
                "若上方有「使用者個人健康檔案」段落，請在建議中明確提及該因素"
                "（年齡 / BMI / 已診斷疾病 / 病歷重點）如何影響此使用者的個人風險，"
                "不要僅給通用建議。"
            )

            answer = None
            if has_llm:
                # max_tokens 從 4096 拉到 8192:使用者反映「話講一半」就停 —
                # 主要原因是 Claude 達 4096 上限後直接截斷在句子中間,而舊
                # call_llm_api 並未偵測 stop_reason='max_tokens',使用者完全
                # 看不出是被截掉的。8192 對 Q&A 已足夠,Claude 帳單照樣只
                # 算實際輸出的 tokens 不會多花錢。
                # timeout 從 25s 拉到 60s:長回應的生成時間可能 30-40s,
                # 25s 容易在中途逾時返回 None,使用者只看到 fallback 摘要。
                answer = call_llm_api(
                    st.session_state.llm_provider,
                    st.session_state.llm_key,
                    full_prompt,
                    st.session_state.llm_model,
                    st.session_state.llm_base_url,
                    system=ANTI_HALLUCINATION_SYSTEM,
                    max_tokens=8192,
                    timeout=60,
                )

            if not answer:
                import data as _data
                err_reason = (getattr(_data, "LAST_LLM_ERROR", "") or "未知")
                why = (f"LLM 失敗：{err_reason}" if has_llm else "未填 LLM 金鑰")
                snap = st.session_state.snapshot
                wt = snap.sort_values("aqi", ascending=False).iloc[0]
                bt = snap.sort_values("aqi").iloc[0]
                answer = (
                    f"⚠ {why}，僅依資料回覆事實摘要：\n\n"
                    f"目前全國平均 AQI **{snap['aqi'].mean():.0f}**。"
                    f"最高：{wt['city']} {wt['aqi']:.0f}（{wt['level']}），"
                    f"最低：{bt['city']} {bt['aqi']:.0f}（{bt['level']}）。"
                )

            st.session_state.chat_history.append({
                "role":    "assistant",
                "content": answer,
                "refs":    picked_refs if has_llm else [],
                "time":    datetime.now().strftime("%H:%M"),
            })

        # Force a fresh script run so st.chat_input resets cleanly and accepts
        # the user's next question without needing a manual page interaction.
        # Without this, the input widget sometimes "sticks" after the long LLM
        # blocking call because the widget state isn't fully refreshed.
        st.rerun()

    # Final render — repaints with no typing dots, including the new reply.
    # References are now embedded as native HTML <details> under each bot
    # reply (see `_bubble_html`), so there is no longer a separate trailing
    # expander widget here.
    _draw(show_typing=False)


def _scroll_chat_to_latest() -> None:
    """把浮動聊天面板的歷史容器瞬間捲到最新一則(LINE:永遠先看到最新訊息)。

    為什麼用 components.html 而不是 st.markdown:
      `st.markdown(unsafe_allow_html=True)` 會把 <script> 過濾掉,腳本根本不會跑。
      components.html 會建一個 same-origin 的 iframe,iframe 內的腳本能透過
      `window.parent.document` 觸及主文件,設定 `.st-key-chat_history` 的 scrollTop。
      height=0 → iframe 不佔可見空間(渲染在主流程末端、畫面外,不影響 panel 版面)。

    時機:每次 fragment rerun(開面板 / 送出訊息 / 收到回覆)都會重新執行此函式 →
    iframe 重建 → 腳本再跑一次 → 自動跟到最新。用兩個 requestAnimationFrame 等
    這一幀 DOM paint 完(bubble 都進 DOM)再讀 scrollHeight,值才是最終高度。
    捲動用瀏覽器預設的「瞬間」行為(非 smooth),避免使用者在意的動畫延遲感。
    """
    from streamlit.components.v1 import html as _components_html
    _components_html(
        """
        <script>
          (function () {
            const doc = window.parent && window.parent.document;
            if (!doc) return;
            const scrollNow = () => {
              const h = doc.querySelector('.st-key-chat_history');
              if (h) { h.scrollTop = h.scrollHeight; }
            };
            requestAnimationFrame(() => requestAnimationFrame(scrollNow));
          })();
        </script>
        """,
        height=0,
    )


# ── Floating chat: either collapsed FAB or expanded panel (never both) ──────
# 包進 @st.fragment 讓「使用者送出訊息 → 呼叫 LLM(25-60s 阻塞)→ 寫入回覆」
# 整段流程只 rerun 這個 fragment,不影響整個 app。沒有 fragment 的話,LLM
# 跑那 25-60 秒 Streamlit 會把整頁標成 running 狀態,儀表板的圖表 / 互動元件
# 全部變灰,使用者抱怨「ai助理回覆時網頁不要暗掉」就是這個。
# 開 / 收用 on_click callback(不用回傳值 + st.rerun):callback 會在 fragment 重跑
# 「之前」就改好 chat_expanded,重跑時直接畫對的分支,只跑一次 rerun。
#
# 重要:fragment 真正的「呼叫點」在主腳本最下方(封面區 + Pipeline 觸發檢查之後),
# 這裡只是 def。把呼叫往後挪,讓 cover/sidebar 的 Pipeline 按鈕按下後,
# 先設好 `chat_expanded=False`,fragment 才會 render FAB(而非聊天 panel),
# 避免 Pipeline 30-60 秒阻塞期間,聊天 panel 還掛在畫面上但點 X 無反應。
def _set_chat_open() -> None:
    st.session_state.chat_expanded = True


def _set_chat_closed() -> None:
    st.session_state.chat_expanded = False


@st.fragment
def _floating_chat_fragment() -> None:
    if st.session_state.chat_expanded:
        with st.container(key="floating_chat"):
            # LINE-style contact bar — avatar + name + online status (the close
            # button below is absolute-positioned to the top-right via CSS in
            # styles.py: .st-key-floating_chat .stButton > button).
            st.markdown(
                "<div class='line-contact-bar'>"
                "<div class='line-contact-avatar'>🤖</div>"
                "<div class='line-contact-info'>"
                "<div class='line-contact-name'>AgentAQI 分析師</div>"
                "<div class='line-contact-status'>"
                "<span class='line-status-dot'></span>"
                "<span>在線 · 隨時待命</span>"
                "</div>"
                "</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            # on_click 在 fragment 重跑「之前」就把 chat_expanded 設 False,因此重跑時
            # 直接走 else 分支畫 FAB,panel(含捲動 iframe)完全不再渲染 → 一次 rerun
            # 收掉,避免「先重畫 panel 再切換」造成的關閉延遲與文字殘留。
            st.button("✕", key="chat_close", help="收起聊天面板", on_click=_set_chat_closed)
            _render_chat_panel()
        # 注意:故意放在 `with st.container(key="floating_chat")` 區塊「之外」,
        # 這樣捲動用的 0 高度 iframe 不會變成 panel 的 flex 子元素去擾亂版面,
        # 它只渲染在主流程末端(畫面外)並透過 window.parent 捲動歷史容器。
        _scroll_chat_to_latest()
    else:
        with st.container(key="fab_container"):
            st.button("💬  AI 助理", key="fab_chat_btn", type="secondary", on_click=_set_chat_open)


# NOTE: _floating_chat_fragment() is now called near the end of the script
# (after Pipeline trigger detection). See app.py 下方「Floating chat 呼叫點」。


# =============================================================================
# 封面區 (Cover Page) — 永遠在頁面最上方
# =============================================================================
# 封面顯示:AgentAQI 品牌標題 + 副標 + 3 個 agent 功能介紹 + 狀態指示
# 大型「啟動 Pipeline」按鈕在這裡,使用者第一次進入時必須點它才會跑 Pipeline。
# 封面下方依序是 SECTION · 01 (Agent 劇場) → 02 (主儀表板) → 03 (24h 趨勢)
# → 04 (污染物剖析) → 05 (環境關聯) → 06 (官方 vs 民間) → 07 (健康預警)
# → 08 (個人化推薦) → 09 (健康日誌) → 10 (Agent Bot)
# =============================================================================
_llm_prov_name = LLM_PROVIDERS[st.session_state.llm_provider]["name"]
_has_llm_key   = bool(st.session_state.llm_key.strip())

if _has_llm_key:
    oc_pill = (
        f"<span class='pill green'><span class='dot'></span>"
        f"{escape(_llm_prov_name)} · LLM 已連線</span>"
    )
else:
    oc_pill = (
        "<span class='pill gray'><span class='dot'></span>"
        "未填 LLM 金鑰 · 仍可看圖表</span>"
    )

data_pill = (
    "<span class='pill cyan'><span class='dot'></span>EPA Open Data + Open-Meteo</span>"
)

# Show pipeline_done as a pill so users always know the state
pipeline_pill = (
    "<span class='pill green'><span class='dot'></span>Pipeline 已完成</span>"
    if st.session_state.pipeline_done else
    "<span class='pill gray'><span class='dot'></span>Pipeline 尚未啟動</span>"
)

st.markdown(
    f"""
    <div class='cover-wrap'>
      <div class='cover-logo'>🤖</div>
      <div class='cover-eyebrow'>TAIWAN AIR QUALITY · MULTI-AGENT SYSTEM</div>
      <div class='cover-title'>AgentAQI 監控平台</div>
      <div class='cover-subtitle'>
        三個 agent 接力即時採集 EPA + 民生公共物聯網資料，由分析師整合 RAG 文獻產出風險研判，
        預警員依你的個人健康檔案給個人化建議。按下啟動鍵，整套儀表板就會在你面前展開。
      </div>
      <div class='cover-features'>
        <div class='cover-feature'><span class='ico'>📡</span> 採集者 · EPA + 民生公共物聯網</div>
        <div class='cover-feature'><span class='ico'>🧠</span> 分析師 · LLM + RAG</div>
        <div class='cover-feature'><span class='ico'>🏥</span> 預警員 · 個人化健康建議</div>
      </div>
      <div class='cover-status'>{data_pill}{oc_pill}{pipeline_pill}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Scoped CSS — only active here (cover area has the prominent CTA)
st.markdown(
    """
    <style>
    .stButton > button[kind="primary"] {
        font-size: 1.25rem !important;
        font-weight: 900 !important;
        padding: 1.1rem 2.5rem !important;
        border-radius: 16px !important;
        letter-spacing: 0.04em !important;
        animation: ctaGlow 2.4s ease-in-out infinite;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px) scale(1.02);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── 步驟 ① 個人健康檔案(在啟動 Pipeline「之前」填)──────────────────────────
# 填好再啟動 → 分析師 / 預警員第一次跑就用 persona,且會匯出
# 進 latest_aqi.json 供 Hermes 拉取。SECTION 08 只負責呈現結果。
_render_persona_step1()

cL, cC, cR = st.columns([3, 2, 3])
with cC:
    cover_run = st.button(
        ("↻  重新執行 Pipeline" if st.session_state.pipeline_done
         else "▶  啟動三代理人 Pipeline"),
        key="cover_launch",
        type="primary",
        use_container_width=True,
    )
    st.markdown(
        "<div class='cover-hint' style='text-align:center;'>"
        "▼ 點擊啟動即可看到 3-agent 協作與群組聊天室 ▼"
        "</div>",
        unsafe_allow_html=True,
    )

# Anchor for auto-scroll once user clicks launch — the theater section below
# uses #theater-anchor as its scroll target.
st.markdown("<div id='theater-anchor'></div>", unsafe_allow_html=True)

# When launched: set a session flag (consumed by the agent section, where
# placeholders for live updates exist) and inject scroll-into-view JS via
# streamlit.components so it actually executes in the browser. We can't call
# run_pipeline() here because the section's placeholders are created later
# in the script — running pipeline at this point would put the progress bar
# above the theater section instead of inside it.
if cover_run or run_clicked:
    st.session_state["_pipeline_should_run"] = True
    import streamlit.components.v1 as _components
    _components.html(
        """
        <script>
        (function () {
          // Wait a beat for Streamlit to settle the layout, then smooth-scroll
          // to the theater anchor that lives in the agent section below.
          setTimeout(function () {
            var doc = window.parent ? window.parent.document : document;
            var anchor = doc.getElementById('theater-anchor');
            if (anchor) anchor.scrollIntoView({behavior: 'smooth', block: 'start'});
          }, 80);
        })();
        </script>
        """,
        height=0,
    )


# ── Floating chat 呼叫點 ────────────────────────────────────────────────────
# 故意放在「Pipeline 觸發檢查之後」、「run_pipeline() 之前」:三個觸發來源
# (sidebar 按鈕 / 封面按鈕 / 每小時自動更新 fragment)都會在到這一行之前把
# `_pipeline_should_run` 設為 True。Pipeline 即將阻塞 Python 30-60 秒
# (LLM 呼叫),那段期間 server 完全卡住,聊天 panel 點 X 沒反應、輸入送不出去。
# 在這裡把 chat_expanded 設 False,fragment 就會 render FAB(無 panel),
# Pipeline 結束後使用者再按 FAB 重新打開即可。zero-regression:Pipeline 沒
# 要跑時這段檢查 no-op。
if st.session_state.get("_pipeline_should_run"):
    st.session_state.chat_expanded = False
_floating_chat_fragment()


# =============================================================================
# Dashboard data handles (used by sections below).
# The hero banner that used to sit here was removed — it duplicated the cover
# page header, had a stale removed-agent tag, and pushed the
# actually-useful agent theater further down the page.
# =============================================================================
snapshot    = st.session_state.snapshot
ts_df       = st.session_state.ts_df            # primary 24h history (EPA preferred)
cams_ts_df  = st.session_state.cams_ts_df       # Open-Meteo CAMS 24h history (always available when reachable)
citizen_df  = st.session_state.citizen_df
data_mode   = st.session_state.data_mode


# =============================================================================
# SECTION · 01 三隻 agent 協作視覺化 (AGENT THEATER)
# =============================================================================
# 左欄:像素風辦公室(三個工作桌,active 那個會發光)+ 採集者清洗報告
# 右欄:狀態指示 + 群組聊天室(顯示 push_log 累積的所有 agent 對話)
# 永遠可見 — Pipeline 還沒跑時也會顯示「inactive 工作桌」讓使用者知道架構。
# =============================================================================
st.markdown("<a id='agents'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 01</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>三隻 agent 的協作視覺化</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>每隻 agent 負責 pipeline 中的一個環節。"
    "啟動後依序亮起，講話泡泡顯示它們對彼此說的話。左側中段即時更新採集者的清洗報告，右側則是 3 個 agent 的群組聊天室。</div>",
    unsafe_allow_html=True,
)

c_left, c_right = st.columns([5, 4])

# Pre-allocate placeholders inside the theater columns so live pipeline
# updates land HERE — not in a floating block above the section.
# Left column (top→bottom): pixel office → cleaning report
# Right column (top→bottom): status pill → chat log (full height, no
# floating progress bar — that turned out to be redundant with the pill +
# chat log and just added visual clutter).
# (Critic card removed in 3-agent refactor — its score didn't gate anything.)
with c_left:
    office_ph   = st.empty()
    cleaning_ph = st.empty()

with c_right:
    status_ph = st.empty()
    st.markdown(
        "<div class='eyebrow' style='margin-top:0.1rem;'>🤖 #aqi-agents · 群組聊天室</div>"
        "<div class='tiny muted' style='margin-bottom:0.4rem;'>誰把資料傳給誰 · 即時推播</div>",
        unsafe_allow_html=True,
    )
    chat_ph = st.empty()

# Initial paint reflects current session_state (idle if pipeline hasn't run).
_paint_office(office_ph, st.session_state.active_agent)
_paint_cleaning(cleaning_ph)
_paint_chat(chat_ph)

# If the cover/sidebar button set the run flag earlier this render, kick off
# the pipeline NOW with the section's placeholders so all live updates show
# up inside the theater. After it finishes we do a final rerun so the
# dashboard sections (gated on pipeline_done) render cleanly.
if st.session_state.pop("_pipeline_should_run", False):
    run_pipeline(
        office_ph=office_ph,
        cleaning_ph=cleaning_ph,
        chat_ph=chat_ph,
        progress_ph=None,
        status_ph=status_ph,
    )
    st.rerun()

# Per-agent LLM output cards (visible after pipeline runs).
# 過去同時顯示分析師(B)與預警員(C)兩份報告並排,但預警員的內容下方
# 「健康預警 · 個人化建議」section 已經為每個城市展開個人建議,在這裡再重複
# 出現會冗贅。使用者要求「全代理人分析報告只給分析師報告就好」。
if st.session_state.pipeline_done and st.session_state.llm_analysis:
    prov_label = LLM_PROVIDERS.get(st.session_state.llm_provider, {}).get("name", "LLM").upper() if st.session_state.llm_key.strip() else "FALLBACK"

    def _strip_redundant_heading(text: str) -> str:
        """Strip LLM-generated top-level title that duplicates our eyebrow.

        Some LLMs prepend '# 🚨 空氣品質健康預警通知' or '## 風險分析報告' —
        that's redundant because we already render an eyebrow above the expander.
        Past bug:過去用 while loop 一直 pop heading,結果把第一個 section heading
        (`## ① 現況摘要`)也吃掉,使用者看到報告大標題直接從 ② 開始。
        修法:只 strip 第一個 heading 行(且該行不含節編號 ①②③ / 1./2./3.)。
        節編號的 heading 是真正的章節標題,必須保留。
        """
        text = (text or "").strip()
        if not text:
            return ""
        lines = text.split("\n")
        # Look at the very first non-blank line only
        first_idx = 0
        while first_idx < len(lines) and not lines[first_idx].strip():
            first_idx += 1
        if first_idx >= len(lines):
            return ""
        first = lines[first_idx].lstrip()
        is_heading = first.startswith(("# ", "## ", "### "))
        # 節編號符號:① ② ③ ④ ⑤ ⑥ ⑦ ⑧ ⑨ ⑩ 或 數字+「.、) 」
        has_section_marker = any(ch in first for ch in "①②③④⑤⑥⑦⑧⑨⑩") or bool(
            re.match(r"^#+\s*\d+[\.\)、]", first)
        )
        if is_heading and not has_section_marker:
            # 純粹的 redundant title — 把它跟後面的 blank line 拿掉
            drop_to = first_idx + 1
            while drop_to < len(lines) and not lines[drop_to].strip():
                drop_to += 1
            lines = lines[drop_to:]
        return "\n".join(lines).strip()

    st.markdown(
        f"<div class='eyebrow' style='margin-top:1rem;'>{prov_label} · 全代理人分析報告</div>",
        unsafe_allow_html=True,
    )

    # 單欄展示分析師(B)報告 — 預警員(C)的敏感族群建議下方有專屬 section,
    # 在這裡不再重複顯示。Streamlit-native expander 會正確 render markdown
    # (heading / 表格 / 清單),避免原本 escape-into-pre-wrap 的醜版面。
    with st.expander("🤖 分析師 · 風險分析", expanded=False):
        st.markdown(_strip_redundant_heading(st.session_state.llm_analysis))

    st.markdown(
        "<div class='tiny muted' style='margin-top:0.4rem;'>📚 RAG 引用：WHO 2021 / EPA NAAQS / Lancet 2023 / 台灣 AQI 標準</div>",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# Gate: dashboard sections (02 onwards) only render after pipeline runs.
# Theater section above already handles its own empty state.
# =============================================================================
if not st.session_state.pipeline_done or snapshot is None:
    st.stop()

# ── 期末 demo 數據來源切換 ──────────────────────────────────────────────────
# 若偵測到 scripts/seed_demo_data.py 灌入的 demo 資料(放在隔離的 source='demo'),
# 所有「歷史 AQI」讀取改讀 demo source —— 這樣使用者即使在 demo 中途重跑真實
# Pipeline(會寫 source='cams_hourly'),demo 的 7 天趨勢 / 比上週徽章 / 症狀散點
# 也不會被覆蓋。沒有 demo 資料時讀真實 'cams_hourly'(零回歸)。
_demo_on   = tsdb.has_demo_data()
_aqi_src   = ["demo"] if _demo_on else ["cams_hourly"]
_diary_src = "demo" if _demo_on else "cams_hourly"

# ── 資料新鮮度:顯示「絕對資料時間」而非「X 分鐘前」 ─────────────────────────
# snapshot 每城的 updated_min_ago 是「抓取那一刻」EPA 測站的落後分鐘 — 寫進 snapshot
# 後就固定了。相對顯示(「42 分鐘前」)需要頁面活著去遞增才誠實;改成顯示絕對時間:
#   資料時間 ≈ last_pipeline_run_at − updated_min_ago(該城 EPA 發布時刻)
# 絕對時間永遠為真,頁面閒置多久都不會變成謊言。_elapsed_min(距抓取已過分鐘)仍
# 保留 —— 只用來算新鮮度「燈號顏色」(資料真實年齡 = 抓取時落後 + 閒置經過)。
_last_run = st.session_state.get("last_pipeline_run_at")
_elapsed_min = int((datetime.now() - _last_run).total_seconds() // 60) if _last_run else 0


def _data_time_str(lag_min, fmt: str = "%H:%M") -> str:
    """該筆資料的絕對時間(≈ EPA 發布時刻)= 抓取時間 − 抓取時落後分鐘。"""
    if _last_run is None:
        return "—"
    return (_last_run - timedelta(minutes=int(lag_min))).strftime(fmt)

# =============================================================================
# SECTION · 02 即時 AQI 主儀表板 (MAIN DASHBOARD)
# =============================================================================
# 整個應用的核心 — Pipeline 跑完後最重要的視覺化區域。包含:
#   - 時間軸 slider:可拖動看過去 24h 的歷史快照
#   - 「現在 X · EPA 資料時間 Y · 24h 歷史最新整點 Z」新鮮度標籤(一律絕對時間)
#   - 第一列:聚焦城市資訊 + 城市排名長條圖
#   - 第二列:台灣地圖散點 + PM2.5 vs AQI 散點
#   - 第三列:20 個城市的資料時間卡片(燈號依資料真實年齡:<45min 綠 / <90 黃 / 其他橘)
#   (24h 熱力圖與 7 天紀錄板在 SECTION 03)
# =============================================================================
st.markdown("<a id='dash'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 02</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>主儀表板 · 即時空品總覽</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>預設聚焦<b>你的城市</b>(封面步驟①可改) · 點擊「城市排行」橫條圖可改鎖定任何城市 · "
    "其他圖表會同步高亮 · 拖動下方時間軸看過去 24h 的快照</div>",
    unsafe_allow_html=True,
)

# ── Time-axis scrubber ───────────────────────────────────────────────────
# Pull all available hours from ts_df. ts_df has 25 hourly snapshots (24h history + now).
if ts_df is not None and not ts_df.empty:
    hourly_timestamps = sorted(ts_df["timestamp"].unique())
    if len(hourly_timestamps) > 1:
        time_labels = [pd.Timestamp(ts).strftime("%m/%d %H:00") for ts in hourly_timestamps]
        scrub_default = len(time_labels) - 1   # default to the most recent hour ("now")
        scrub_idx = st.slider(
            "🕒 時間軸",
            min_value=0,
            max_value=len(time_labels) - 1,
            value=scrub_default,
            format="",
            help="拖動可看過去 24 小時任一時點的快照 · 圖表會即時跟隨變化",
            label_visibility="collapsed",
        )
        selected_ts = hourly_timestamps[scrub_idx]
        is_current = scrub_idx == scrub_default
        # Build a reconstructed snapshot for the selected hour
        if not is_current:
            hist_slice = ts_df[ts_df["timestamp"] == selected_ts].copy()
            # Merge with current snapshot to keep geo/region/color fields,
            # but override AQI/pollutants/risk from the historical slice.
            # Only merge columns that actually exist in the history frame —
            # different sources (EPA aqx_p_488 vs CAMS) may report
            # different subsets, and we don't want a KeyError on the slice.
            _override_cols = [
                c for c in ["aqi", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "risk"]
                if c in hist_slice.columns
            ]
            scrub_snapshot = snapshot.merge(
                hist_slice[["city_id"] + _override_cols]
                    .rename(columns={c: f"_h_{c}" for c in _override_cols}),
                on="city_id", how="left",
            )
            for c in _override_cols:
                hist_col = f"_h_{c}"
                if hist_col in scrub_snapshot.columns:
                    scrub_snapshot[c] = scrub_snapshot[hist_col].fillna(scrub_snapshot[c])
                    scrub_snapshot = scrub_snapshot.drop(columns=[hist_col])
            # Recompute color + level based on rewritten AQI
            scrub_snapshot["level"]    = scrub_snapshot["aqi"].apply(lambda v: aqi_to_level(v)["name"])
            scrub_snapshot["color"]    = scrub_snapshot["aqi"].apply(lambda v: aqi_to_level(v)["color"])
            scrub_snapshot["level_num"]= scrub_snapshot["aqi"].apply(lambda v: aqi_to_level(v)["level"])
            snapshot = scrub_snapshot   # rebind for the rest of dashboard
            st.markdown(
                f"<div class='tiny muted' style='text-align:center; margin-top:-0.2rem; margin-bottom:0.4rem;'>"
                f"📸 顯示 <b style='color:#ff8c42;'>{time_labels[scrub_idx]}</b> 的歷史快照 · "
                f"拖到最右側回到即時"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            now_local = datetime.now()
            data_dt = pd.Timestamp(hourly_timestamps[-1]).to_pydatetime()
            history_delay_min = max(0, int((now_local - data_dt).total_seconds() // 60))
            # ── 兩個獨立的「新鮮度」訊號 ────────────────────────────────────
            # 1. snapshot 新鮮度(aqx_p_432 即時測站):決定主儀表板的 emoji
            #    使用者看到的「目前 AQI 55」是這個來源,所以這個 lag 才是真正的
            #    「現在資料新不新」。aqx_p_432 約每 30 分鐘更新一次,< 60 分鐘 = 正常。
            # 2. 24h history 新鮮度(aqx_p_488 / CAMS hourly):純粹給時間軸 scrub 用
            #    這兩個資料集的 publish 延遲常常 4-10 小時(早上 9 點還沒 publish
            #    凌晨的資料),這是上游 API 的特性,不是 app 的 bug。
            try:
                _lag0 = int(snapshot["updated_min_ago"].mean())
            except Exception:
                _lag0 = None
            epa_lag = (_lag0 if _lag0 is not None else 999) + _elapsed_min
            # emoji / 顏色 跟著 snapshot lag(實際使用者看到的數據新鮮度)
            if epa_lag < 60:
                freshness_emoji, freshness_color = "🟢", "#00e676"
                freshness_label = "即時"
            elif epa_lag < 120:
                freshness_emoji, freshness_color = "🟡", "#ffd93d"
                freshness_label = "略有延遲"
            else:
                freshness_emoji, freshness_color = "🔴", "#ff4757"
                freshness_label = "資料延遲較久"
            # 24h 歷史 lag 用中性顏色描述 — 它只影響時間軸 scrub / 趨勢圖,不影響
            # 主畫面的當下 AQI。lag 久的時候給 hint 解釋為什麼。
            if history_delay_min < 90:
                history_hint = ""
            elif history_delay_min < 360:
                history_hint = " <span class='tiny muted'>(上游 EPA aqx_p_488 / CAMS 整點歷史資料的 publish 延遲,屬正常)</span>"
            else:
                history_hint = (
                    " <span class='tiny muted'>(EPA aqx_p_488 與 CAMS 都還沒 publish 凌晨的整點資料,"
                    "下方時間軸 scrub 拖到最新時間點就是此時刻 — 跟你看到的當下 AQI 無關)</span>"
                )
            st.markdown(
                f"<div class='tiny muted' style='text-align:center; margin-top:-0.2rem; margin-bottom:0.4rem; line-height:1.6;'>"
                f"{freshness_emoji} <b style='color:{freshness_color};'>{freshness_label}</b> · "
                f"現在 <b>{now_local.strftime('%m/%d %H:%M')}</b> · "
                f"EPA 即時測站資料時間 <b>{_data_time_str(_lag0, '%m/%d %H:%M') if _lag0 is not None else '—'}</b>(當下 AQI 來源)"
                f"<br>"
                f"24h 歷史最新整點:<b style='color:#00d9ff;'>{time_labels[-1]}</b>{history_hint}"
                f"</div>",
                unsafe_allow_html=True,
            )

# ── 預設聚焦 =「你的城市」(個人化錨點)─────────────────────────────────
# 個人化不該只活在 SECTION 08 之後:一打開儀表板,儀表 / 排行 / 地圖 / 散點的
# 錨點就是你的城市;點「城市排行」仍可隨時切換聚焦任何城市(全台監控保留)。
# 你的城市不在快照時(理論上不會發生)才退回「當前最高 AQI」的全國視角。
focus_id = st.session_state.selected_city
if focus_id and not (snapshot["city_id"] == focus_id).any():
    focus_id = None   # 舊點選的城市不在本輪快照(資料來源變動)→ 回到預設錨點,避免 IndexError
if focus_id:
    _focus_label = "聚焦城市"
else:
    _uc = st.session_state.get("user_city", "taipei")
    if (snapshot["city_id"] == _uc).any():
        focus_id, _focus_label = _uc, "📍 你的城市（預設聚焦）"
    else:
        _focus_label = "當前最高 AQI"
focus_row = snapshot[snapshot["city_id"] == focus_id].iloc[0] if focus_id else snapshot.sort_values("aqi", ascending=False).iloc[0]

# ── 個人 AQI 預警橫幅 (P1 #1) ──────────────────────────────────────────
# 比對使用者「我的城市」AQI 與個人預警閾值,超過即顯示醒目橫幅。
# 同時用 tsdb.city_period_avg 計算「比上週同期 +X%」(P1 #4 歷史對比 highlight)。
_my_city_id = st.session_state.get("user_city", "taipei")
_my_threshold = int(st.session_state.get("user_aqi_threshold", 100))
_my_row = snapshot[snapshot["city_id"] == _my_city_id]
if not _my_row.empty:
    _my_aqi = float(_my_row.iloc[0]["aqi"])
    _my_name = _my_row.iloc[0]["city"]
    _my_level = _my_row.iloc[0]["level"]
    _my_color = _my_row.iloc[0]["color"]

    # 歷史對比:本週(168h)平均 vs 上週(同窗寬)平均
    try:
        _this_avg, _prev_avg, _this_n, _prev_n = tsdb.city_period_avg(_my_city_id, this_hours=168, sources=_aqi_src)
    except Exception:
        _this_avg, _prev_avg, _this_n, _prev_n = None, None, 0, 0
    if _this_avg is not None and _prev_avg is not None and _prev_avg > 0:
        _delta_pct = (_this_avg - _prev_avg) / _prev_avg * 100
        if _delta_pct >= 3:
            _trend_badge = f"<span style='color:#ff8c42; font-weight:700;'>↑ 比上週 +{_delta_pct:.0f}%</span>"
        elif _delta_pct <= -3:
            _trend_badge = f"<span style='color:#00e676; font-weight:700;'>↓ 比上週 {_delta_pct:.0f}%</span>"
        else:
            _trend_badge = f"<span style='color:#8b95a8;'>≈ 與上週相當({_delta_pct:+.0f}%)</span>"
    else:
        _trend_badge = "<span style='color:#8b95a8;'>歷史資料不足無法對比</span>"

    if _my_aqi > _my_threshold:
        # 突破閾值 — 紅色顯眼橫幅 + 動畫
        st.markdown(
            f"<div style='margin:0.6rem 0 1rem 0; padding:0.9rem 1.2rem; "
            f"background:linear-gradient(90deg, rgba(255,71,87,0.20), rgba(155,89,255,0.10)); "
            f"border-left:4px solid #ff4757; border-radius:0 12px 12px 0; "
            f"box-shadow:0 0 24px rgba(255,71,87,0.25);'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.8rem;'>"
            f"<div>"
            f"<span style='font-size:1.05rem; font-weight:800; color:#ff4757;'>⚠ 你的城市突破預警閾值</span>"
            f"<span style='color:#c0c8d8; margin-left:0.6rem;'>"
            f"<b>{_my_name}</b> 目前 AQI <b style='color:{_my_color};'>{_my_aqi:.0f}</b>"
            f"(<span style='color:{_my_color};'>{_my_level}</span>),"
            f"已超過你的預警值 <b>{_my_threshold}</b>"
            f"</span>"
            f"</div>"
            f"<div class='tiny'>{_trend_badge}</div>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        # 未突破 — 淡色資訊條,只顯示城市現況 + 歷史對比
        st.markdown(
            f"<div style='margin:0.4rem 0 0.8rem 0; padding:0.55rem 1rem; "
            f"background:rgba(15,24,48,0.5); border-left:3px solid {_my_color}; "
            f"border-radius:0 8px 8px 0; display:flex; justify-content:space-between; "
            f"align-items:center; flex-wrap:wrap; gap:0.6rem;'>"
            f"<div class='tiny'>"
            f"📍 你的城市 <b>{_my_name}</b>:AQI <b style='color:{_my_color};'>{_my_aqi:.0f}</b>"
            f"(<span style='color:{_my_color};'>{_my_level}</span>)"
            f" · 預警閾值 {_my_threshold}"
            f"</div>"
            f"<div class='tiny'>{_trend_badge}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# Top row: Gauge + ranking
d1, d2 = st.columns([3, 5])

with d1:
    st.markdown(
        f"<div class='eyebrow'>{_focus_label}</div>"
        f"<div style='font-size:1.4rem; font-weight:800; color:{focus_row['color']}; "
        f"text-shadow:0 0 12px {focus_row['color']}55; margin-bottom:-0.3rem;'>"
        f"{focus_row['city']}</div>"
        f"<div class='tiny muted' style='margin-bottom:0.5rem;'>{focus_row['level']} · {focus_row['region']}</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(make_aqi_gauge(focus_row["aqi"], focus_row["city"]),
                     width='stretch', key=f"gauge_{focus_row['city_id']}",
                     config={"displayModeBar": False})

    # Open the city deep-dive as a modal so the user keeps their scroll
    # position on the main dashboard instead of being teleported to another
    # page. (歷史:原 pages/1_城市深入.py 已於 2026-05-13 移除,共用渲染
    # 邏輯整段搬到此 modal,走 _city_detail.py。)
    @st.dialog("🤖 城市深入", width="large")
    def _city_detail_modal(city_id: str):
        from _city_detail import render_city_detail
        render_city_detail(
            initial_city_id=city_id,
            snapshot=st.session_state.snapshot,
            ts_df=st.session_state.ts_df,
            key_prefix="modal_detail",
            show_city_selector=True,
        )

    if st.button(f"🔍 查看 {focus_row['city']} 詳細", use_container_width=True, key="drill_in"):
        _city_detail_modal(focus_row["city_id"])

    # Mini stats
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>PM2.5</div>"
            f"<div class='kpi-value' style='font-size:1.4rem;'>{focus_row['PM2.5']}</div>"
            f"<div class='kpi-sub'>μg/m³</div></div>",
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>O₃</div>"
            f"<div class='kpi-value orange' style='font-size:1.4rem;'>{focus_row['O3']}</div>"
            f"<div class='kpi-sub'>ppb</div></div>",
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>風險分數</div>"
            f"<div class='kpi-value' style='font-size:1.4rem; color:#9b59ff; text-shadow:0 0 12px rgba(155,89,255,0.4);'>{focus_row['risk']:.0f}</div>"
            f"<div class='kpi-sub'>/100</div></div>",
            unsafe_allow_html=True,
        )

with d2:
    st.markdown("<div class='eyebrow'>城市 AQI 排行</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>點擊長條鎖定城市，全局聯動篩選</div>", unsafe_allow_html=True)

    event = st.plotly_chart(
        make_city_ranking(snapshot, focus_id),
        width='stretch', key="ranking",
        on_select="rerun", selection_mode="points",
        config={"displayModeBar": False},
    )
    if event and event.get("selection") and event["selection"].get("points"):
        pt = event["selection"]["points"][0]
        # The bar's y value is city name
        ranked = snapshot.sort_values("aqi", ascending=True).reset_index(drop=True)
        idx = pt.get("point_index", 0)
        if 0 <= idx < len(ranked):
            new_city = ranked.iloc[idx]["city_id"]
            if new_city != st.session_state.selected_city:
                st.session_state.selected_city = new_city
                st.rerun()

# Second row: Map + Scatter PM2.5 vs AQI
m1, m2 = st.columns([5, 4])

with m1:
    st.markdown("<div class='eyebrow'>地理分佈</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='tiny muted' style='margin-bottom:0.4rem;'>"
        "圓圈大小反映 AQI，顏色反映等級 · "
        "<b style='color:#00d9ff;'>來源：EPA aqx_p_432</b>（環境部測站即時值）"
        "</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(make_map(snapshot, focus_id), width='stretch', key="map",
                     config={"displayModeBar": False})

with m2:
    st.markdown("<div class='eyebrow'>PM2.5 × AQI × 風險</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>氣泡大小代表風險分數</div>", unsafe_allow_html=True)
    st.plotly_chart(make_pm25_aqi_scatter(snapshot, focus_id),
                     width='stretch', key="scatter",
                     config={"displayModeBar": False})

# Third row: Data freshness
st.markdown("<div class='eyebrow' style='margin-top:0.8rem;'>各城市資料新鮮度</div>", unsafe_allow_html=True)

fresh_cards = "".join(
    f"<div class='kpi-card' style='min-width:128px; {'border:1px solid #00d9ff; box-shadow:0 0 18px rgba(0,217,255,0.4);' if focus_id == row['city_id'] else ''}'>"
    f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
    f"<div class='tiny' style='font-weight:700; color:#e8eef7;'>{row['city']}</div>"
    f"<div style='width:7px; height:7px; border-radius:50%; background:{'#00e676' if _m < 45 else ('#ffd93d' if _m < 90 else '#ff8c42')}; box-shadow:0 0 6px {'#00e676' if _m < 45 else ('#ffd93d' if _m < 90 else '#ff8c42')};'></div>"
    f"</div>"
    f"<div style='font-family:JetBrains Mono; color:{'#00e676' if _m < 45 else ('#ffd93d' if _m < 90 else '#ff8c42')}; font-size:0.95rem; font-weight:700; margin-top:0.3rem;'>{_t}</div>"
    f"<div class='tiny muted'>AQI {row['aqi']:.0f}</div>"
    f"</div>"
    for _, row in snapshot.iterrows()
    for _m in (int(row['updated_min_ago']) + _elapsed_min,)   # 資料真實年齡(只決定燈號顏色)
    for _t in (_data_time_str(row['updated_min_ago']),)       # 絕對資料時間(顯示用)
)
st.markdown(
    f"<div style='display:flex; gap:0.6rem; flex-wrap:wrap;'>{fresh_cards}</div>",
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# SECTION · 03 24 小時趨勢 (TRENDS)
# =============================================================================
# 多城市的 24h AQI 趨勢線圖。使用者可在 multiselect 選擇要比較的城市。
# 原本右側還有 6h AQI 預測,但 2026-05-13 移除(np.random 合成預測、非真實,會誤導)。
# =============================================================================
st.markdown("<a id='trend'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 03</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>24 小時趨勢</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>過去 24 小時的 AQI 走勢 — 預設只放<b>你的城市</b>,要比較再多選；"
    "點「城市排行」鎖定的城市也會自動加入(📍 粗線)。</div>",
    unsafe_allow_html=True,
)

st.markdown("<div class='eyebrow'>24 小時 AQI 趨勢</div>", unsafe_allow_html=True)
selected = st.multiselect(
    "選擇要顯示的城市",
    options=[c["id"] for c in CITIES],
    default=st.session_state.trend_cities,
    format_func=lambda cid: CITY_BY_ID[cid]["name"],
    key="trend_select",
    label_visibility="collapsed",
)
if selected != st.session_state.trend_cities:
    st.session_state.trend_cities = selected
# Show every selected city (no cap) so "select all" actually displays all
# 20 cities. Plotly handles 20 traces fine — its built-in legend toggles
# let the user mute lines per-city if the chart gets too busy.
show_ids = list(dict.fromkeys((selected or []) + ([focus_id] if focus_id else []))) or selected
if show_ids:
    st.plotly_chart(make_trend_line(ts_df, show_ids, highlight=focus_id),
                     width='stretch', key="trend_line",
                     config={"displayModeBar": False})
else:
    st.info("請至少選擇一個城市以顯示趨勢")

# Heatmap — 官方測站 (EPA aqx_p_488) 與 模型 (Open-Meteo CAMS) 雙軌呈現
st.markdown("<div class='eyebrow' style='margin-top:0.8rem;'>24h × 20 城市熱力時序圖</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='tiny muted' style='margin-bottom:0.4rem;'>"
    "切換來源比對 — <b style='color:#00d9ff;'>EPA 官方測站</b> 為環境部 77 站每小時實測；"
    "<b style='color:#ffb380;'>CAMS 模型</b> 為歐洲哥白尼大氣監測模式（衛星同化）的網格產出。"
    "兩者皆為真實外部資料，<u>非合成</u>。"
    "</div>",
    unsafe_allow_html=True,
)
with st.expander("📖 三個 AQI 來源差異對照表（為什麼地理分佈 vs 熱力圖會不同？）"):
    st.markdown(
        """
| 圖表 | API 端點 | 性質 | 更新頻率 | 涵蓋 |
|---|---|---|---|---|
| **地理分佈** | EPA `aqx_p_432` | 官方測站**即時**單筆值 | 每小時 | 77 個實體測站 |
| **熱力圖 EPA tab** | EPA `aqx_p_488` | 官方測站**過去 24h** 逐小時 | 每小時(歷史延遲 1-2h) | 77 個實體測站 |
| **熱力圖 CAMS tab** | Open-Meteo CAMS | 衛星**同化模式**網格 | 每小時 | 全境網格(非測站) |

**結論**:這三者是**三個不同的資料來源**,同一城市同時間的 AQI 數值會有差異是預期行為。
EPA 即時(432)反映**測站當下**;EPA 歷史(488)用於**追蹤趨勢**;CAMS 用於**填補無測站區域**。
"""
    )
_heat_tab_epa, _heat_tab_cams = st.tabs(["🏛 EPA 官方測站", "🌫 CAMS 大氣模式"])
with _heat_tab_epa:
    if ts_df is not None and not ts_df.empty:
        st.plotly_chart(make_heatmap(ts_df, highlight_city=focus_row["city"]),
                         width='stretch', key="heatmap_epa",
                         config={"displayModeBar": False})
    else:
        st.info("EPA 歷史資料未取得（請確認 sidebar 已填 EPA api_key）— 改看右側 CAMS tab。")
with _heat_tab_cams:
    if cams_ts_df is not None and not cams_ts_df.empty:
        st.plotly_chart(make_heatmap(cams_ts_df, highlight_city=focus_row["city"]),
                         width='stretch', key="heatmap_cams",
                         config={"displayModeBar": False})
        st.caption("資料來源：Open-Meteo · Copernicus CAMS Atmospheric Composition Reanalysis")
    else:
        st.info("Open-Meteo CAMS 歷史資料未取得（網路問題或 API 暫時故障）。")

# ── 本週 AQI 記錄板（從本機 SQLite 時序快取算）─────────────────────────────
# Reads the past 7 days of CAMS-hourly data stored in SQLite (seeded each
# pipeline run) and shows the cities with the highest peak AQI. Gives the
# user a "where did air quality get bad this week, even if it's clean now"
# view, which the current-snapshot ranking can't provide.
_week_top = tsdb.top_cities_by_period(hours=168, top_n=10, sources=_aqi_src)
st.markdown(
    "<div class='eyebrow' style='margin-top:1.2rem;'>📊 過去 7 天 AQI 紀錄板（本機時序快取）</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='tiny muted' style='margin-bottom:0.5rem;'>"
    "資料來自本機 SQLite 累積的 <b>CAMS 模式</b>逐時歷史(每跑一次 Pipeline 補齊最新一週)。"
    "「全台排行」大數字 = 各城<b>本週最高小時 AQI(峰值)</b>;"
    "「所選城市」逐日卡大數字 = <b>當天 24 小時平均</b>。"
    "</div>",
    unsafe_allow_html=True,
)
# 兩種視角可切換:全台排行(本週哪裡最差)/ 所選城市的 7 天逐日紀錄(個人化錨點)
_board_mode = st.radio(
    "紀錄板視角",
    options=["🏆 全台週峰值排行", f"📍 {focus_row['city']} 的 7 天紀錄"],
    horizontal=True,
    label_visibility="collapsed",
    key="week_board_mode",
)
if _board_mode.startswith("🏆"):
    if _week_top is None or _week_top.empty:
        st.info("時序快取還沒有累積資料 — 跑一次 Pipeline 就會自動拉 CAMS 過去 7 天進來。")
    else:
        rank_cols = st.columns(min(5, len(_week_top)))
        for idx, (col, row) in enumerate(zip(rank_cols, _week_top.head(5).itertuples(index=False))):
            level = aqi_to_level(row.max_aqi)
            col.markdown(
                f"<div class='kpi-card' style='min-width:0; border-color:{level['color']}44;'>"
                f"<div class='kpi-label'>#{idx+1} · {escape(row.city)} · 週峰值</div>"
                f"<div class='kpi-value' style='color:{level['color']}; font-size:1.6rem;'>{row.max_aqi:.0f}</div>"
                f"<div class='kpi-sub'>週平均 {row.avg_aqi:.0f}（{int(row.n_hours)}h 樣本）</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        # Detail expander with the full top-10 table
        with st.expander(f"查看完整 top-{len(_week_top)} 表 + 平均/最低 AQI", expanded=False):
            _disp = _week_top.rename(columns={
                "city": "城市", "max_aqi": "週峰值",
                "avg_aqi": "週平均", "min_aqi": "週最低", "n_hours": "樣本小時數",
            })[["城市", "週峰值", "週平均", "週最低", "樣本小時數"]]
            st.dataframe(
                _disp.style.background_gradient(subset=["週峰值"], cmap="RdYlGn_r"),
                use_container_width=True,
                height=60 + 32 * len(_disp),
            )
else:
    # 📍 所選城市視角:7 天逐日卡(均值著色)+ 展開看逐時曲線
    _hist7 = tsdb.city_history(focus_id, hours=168, sources=_aqi_src)
    if _hist7 is None or _hist7.empty:
        st.info(f"時序快取還沒有 {focus_row['city']} 的資料 — 跑一次 Pipeline 會自動拉 CAMS 過去 7 天回來。")
    else:
        _daily7 = (_hist7.assign(_d=_hist7["ts"].dt.strftime("%m/%d"))
                          .groupby("_d", sort=True)["aqi"]
                          .agg(["mean", "max", "min"]).round(1))
        day_cols = st.columns(len(_daily7))
        for col, (_d, _r) in zip(day_cols, _daily7.iterrows()):
            _lv = aqi_to_level(_r["mean"])
            col.markdown(
                f"<div class='kpi-card' style='min-width:0; border-color:{_lv['color']}44;'>"
                f"<div class='kpi-label'>{_d} · 日均</div>"
                f"<div class='kpi-value' style='color:{_lv['color']}; font-size:1.6rem;'>{_r['mean']:.0f}</div>"
                f"<div class='kpi-sub'>峰 {_r['max']:.0f} · 低 {_r['min']:.0f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with st.expander(f"{focus_row['city']} 7 天逐時曲線（{len(_hist7)} 筆 hourly）", expanded=False):
            import plotly.graph_objects as _go
            _figw = _go.Figure()
            _figw.add_trace(_go.Scatter(
                x=_hist7["ts"], y=_hist7["aqi"], mode="lines",
                line=dict(color="#00d9ff", width=2),
                hovertemplate="%{x|%m/%d %H:%M}<br>AQI: <b>%{y:.1f}</b><extra></extra>",
            ))
            _figw.update_layout(
                height=260,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter, sans-serif", color="#e8eef7", size=11),
                margin=dict(l=40, r=20, t=10, b=30),
                xaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8")),
                yaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8"), title="AQI"),
            )
            st.plotly_chart(_figw, use_container_width=True,
                            config={"displayModeBar": False}, key="week_city_hist")

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# 污染物深入區 (POLLUTANTS) — 多城市污染物比較
# =============================================================================
# 雷達圖 + 堆疊長條圖,看「哪個城市主要被哪種污染物推起來」。
# 雷達圖把 6 種污染物的相對強度畫在同一張圖;
# 堆疊圖則顯示每個城市的「污染物組成比例」。
# =============================================================================
st.markdown("<a id='pollute'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 04</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>污染物剖析</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>六種主要污染物的雷達圖比較與堆疊組成。"
    "雷達圖的軸是標準化過的（相對 WHO/EPA 指引值），所以越外圈越糟。</div>",
    unsafe_allow_html=True,
)

p1, p2 = st.columns([4, 5])

with p1:
    st.markdown("<div class='eyebrow'>污染物雷達圖</div>", unsafe_allow_html=True)
    radar_cities = st.multiselect(
        "比較城市（最多 4 個）",
        options=[c["id"] for c in CITIES],
        default=st.session_state.radar_cities,
        format_func=lambda cid: CITY_BY_ID[cid]["name"],
        max_selections=4,
        key="radar_select",
        label_visibility="collapsed",
    )
    show_radar = radar_cities if radar_cities else st.session_state.radar_cities
    if show_radar:
        st.plotly_chart(make_pollutant_radar(snapshot, show_radar, highlight=focus_id),
                         width='stretch', key="radar",
                         config={"displayModeBar": False})

with p2:
    st.markdown("<div class='eyebrow'>各城市污染物組成</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>標準化後堆疊，顯示哪種污染物是該城市的主要貢獻者</div>", unsafe_allow_html=True)
    st.plotly_chart(make_stacked_composition(snapshot, highlight=focus_id),
                     width='stretch', key="stacked",
                     config={"displayModeBar": False})

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# 環境因子區 (ENVIRONMENT) — 氣象與 AQI 的相關性分析
# =============================================================================
# 風玫瑰圖(8 方位的城市風向分佈,色階 = 該方位平均 AQI)+
# 濕度散點圖(濕度 vs AQI + 線性回歸 + Pearson 相關係數)。
# 用來探討「風向 / 濕度」是否與 AQI 顯著相關。
# =============================================================================
st.markdown("<a id='env'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 05</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>環境關聯</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>風從哪裡來、濕度怎麼跟 AQI 互動。"
    "這些跟空品高度相關但常被忽略的維度，都在這裡。</div>",
    unsafe_allow_html=True,
)

e1, e2 = st.columns(2)

with e1:
    st.markdown("<div class='eyebrow'>風向玫瑰圖</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>橫桿長度=城市數；顏色=該風向的平均 AQI</div>", unsafe_allow_html=True)
    st.plotly_chart(make_wind_rose(snapshot), width='stretch', key="wind",
                     config={"displayModeBar": False})

with e2:
    st.markdown("<div class='eyebrow'>濕度 × AQI 相關性</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>含趨勢線與皮爾森相關係數 · 只標 📍 所選城市與極端值,其餘滑鼠查看</div>", unsafe_allow_html=True)
    st.plotly_chart(make_humidity_scatter(snapshot, highlight=focus_id), width='stretch', key="humid",
                     config={"displayModeBar": False})

# Weather cards
st.markdown("<div class='eyebrow' style='margin-top:0.8rem;'>各城市氣象條件</div>", unsafe_allow_html=True)
weather_remarks = {
    "high_humid": "💧 高濕導致細懸浮微粒吸水膨脹",
    "low_wind":   "🌫 風速低不利擴散",
    "high_temp":  "☀ 高溫易生成臭氧",
    "normal":     "✓ 條件正常",
}

def _weather_card(row) -> str:
    remark = (weather_remarks["high_humid"] if row["humidity"] > 80
              else weather_remarks["low_wind"] if row["wind_speed"] < 2
              else weather_remarks["high_temp"] if row["temp"] > 30
              else weather_remarks["normal"])
    return (
        f"<div class='glass-card' style='min-width:230px; padding:1rem 1.1rem;'>"
        f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
        f"<div style='font-weight:700; font-size:0.95rem;'>{row['city']}</div>"
        f"<div class='tiny muted'>{row['region']}</div>"
        f"</div>"
        f"<div style='display:grid; grid-template-columns:1fr 1fr; gap:0.5rem; margin-top:0.6rem;'>"
        f"<div><div class='tiny muted'>🌡 溫度</div><div style='font-family:JetBrains Mono; font-weight:700; color:#ff8c42;'>{row['temp']}°C</div></div>"
        f"<div><div class='tiny muted'>💧 濕度</div><div style='font-family:JetBrains Mono; font-weight:700; color:#00d9ff;'>{row['humidity']:.0f}%</div></div>"
        f"<div><div class='tiny muted'>💨 風速</div><div style='font-family:JetBrains Mono; font-weight:700; color:#9b59ff;'>{row['wind_speed']} m/s</div></div>"
        f"<div><div class='tiny muted'>📊 氣壓</div><div style='font-family:JetBrains Mono; font-weight:700; color:#00e676;'>{row['pressure']:.0f}</div></div>"
        f"</div>"
        f"<div class='tiny' style='margin-top:0.6rem; padding:0.3rem 0.5rem; background:rgba(0,217,255,0.05); border-left:2px solid #00d9ff; border-radius:0 6px 6px 0;'>{remark}</div>"
        f"</div>"
    )

weather_cards = "".join(_weather_card(row) for _, row in snapshot.iterrows())
st.markdown(
    f"<div style='display:flex; gap:0.7rem; overflow-x:auto; padding-bottom:0.4rem;'>{weather_cards}</div>",
    unsafe_allow_html=True,
)

# NOTE: The "🛰 NASA TROPOMI 衛星觀測" section was removed because we couldn't
# pull real Sentinel-5P data without significant Google Earth Engine /
# Copernicus Data Space setup. The 24h heatmap tabs (above) already show
# real CAMS atmospheric model data which is the closest honest substitute.

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# 資料來源比較 (DATA SOURCES) — 民間 vs 官方
# =============================================================================
# 用並排長條圖比較「官方 EPA 測站 PM2.5」與「民間 LASS-net Airbox PM2.5」
# 在每個城市的差異。理論上應接近,但民間感測器精度較差、放置位置
# (如住家陽台 / 街角)更貼近實際呼吸環境,差異本身就是分析價值。
# =============================================================================
st.markdown("<a id='source'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 06</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>官方測站 vs 民間感測器</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>採集者從<b style='color:#00d9ff;'>環境部 EPA 開放資料</b>拿到的官方測站，"
    "對比民間感測員從<b style='color:#ff8c42;'>民生公共物聯網 SensorThings API</b>（智慧城鄉空品微型感測器網路）"
    "與 <b style='color:#ff8c42;'>LASS-net Airbox</b> 並行拉取的民間感測器。"
    "兩者出現大落差，往往是區域熱點的早期訊號。離島地區（澎湖、金門）"
    "兩套網路皆無部署，會顯示「無民間感測」。</div>",
    unsafe_allow_html=True,
)
st.info(
    "ℹ️ **主畫面的 AQI 一律採官方 EPA**（法定計算、綜合 6 種污染物、每縣市取測站平均）"
    "— 民間感測器**不混入**主數字、只在這一區並排對照。"
    "兩者各有所長:官方權威、有完整 AQI;民間密度高(~1 萬顆)、更貼近街道實際呼吸環境。"
    "我們選擇**呈現差異而非融合成一個數字** — 融合會犧牲可追溯性,且民間多半只量 PM2.5,"
    "硬湊成 AQI 反而失真。",
    icon="ℹ️",
)

# Report LASS cleaning numbers if we have them — real, not made up
_lc = st.session_state.get("lass_cleaning")
_covered = 0
if citizen_df is not None and "sensor_count" in citizen_df.columns:
    _covered = int((citizen_df["sensor_count"] > 0).sum())
if _lc is not None:
    st.markdown(
        f"<div style='display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.6rem;'>"
        f"<span class='tag'>原始 {_lc.raw_records:,} 筆</span>"
        f"<span class='tag green'>保留 {_lc.kept_records:,} 筆</span>"
        f"<span class='tag orange'>丟棄 {_lc.dropped_records:,} 筆</span>"
        f"<span class='tag purple'>覆蓋 {_covered}/{len(CITIES)} 城市</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

s1, s2 = st.columns([5, 3])
with s1:
    st.markdown("<div class='eyebrow'>PM2.5 並排比較</div>", unsafe_allow_html=True)
    st.plotly_chart(make_citizen_vs_official(citizen_df, focus_id),
                     width='stretch', key="cit_vs_off",
                     config={"displayModeBar": False})

with s2:
    st.markdown("<div class='eyebrow'>差距排行</div>", unsafe_allow_html=True)
    # Drop cities with no civilian sensor coverage from the delta ranking
    valid = citizen_df.dropna(subset=["citizen_PM2.5"]).copy()
    if not valid.empty:
        valid["abs_delta"] = valid["delta"].abs()
        sorted_delta = valid.sort_values("abs_delta", ascending=False).head(6)
        rows = "".join(
            f"<div style='display:flex; justify-content:space-between; align-items:center; padding:0.55rem 0.8rem; border-bottom:1px dashed rgba(255,255,255,0.08);'>"
            f"<div><div style='font-weight:700;'>{r['city']}</div>"
            f"<div class='tiny muted'>官 {r['official_PM2.5']:.1f} · 民 {r['citizen_PM2.5']:.1f}（n={int(r['sensor_count'])}）</div></div>"
            f"<div style='font-family:JetBrains Mono; font-weight:800; font-size:1.05rem; color:{'#ff8c42' if abs(r['delta']) > 3 else '#8b95a8'};'>{'+' if r['delta'] >= 0 else ''}{r['delta']:.1f}</div>"
            f"</div>"
            for _, r in sorted_delta.iterrows()
        )
    else:
        rows = (
            "<div style='padding:1rem; text-align:center; color:#8b95a8; font-size:0.85rem;'>"
            "目前所有城市都無民間感測站覆蓋，或 LASS API 未回應。"
            "</div>"
        )
    # No-coverage cities listed separately
    nocover = citizen_df[citizen_df["citizen_PM2.5"].isna()]["city"].tolist()
    if nocover:
        rows += (
            f"<div style='padding:0.5rem 0.8rem; font-size:0.7rem; color:#6a7080;'>"
            f"無覆蓋：{escape('、'.join(nocover))}"
            f"</div>"
        )
    st.markdown(f"<div class='glass-card' style='padding:0.5rem;'>{rows}</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# 健康預警區 (HEALTH) — 個人化健康建議卡片
# =============================================================================
# 改版前:依「5 類敏感族群」(老人/幼童/氣喘/心血管/孕婦)為每個城市印出 5 條
# 罐頭建議。使用者反映「過於籠統」 — 「孕婦」對沒懷孕的人毫無意義,
# 「心血管」對沒病史的人多餘,「氣喘」對沒氣喘的人沒用。
#
# 改版後流程:
#   1. 檢查使用者是否填過封面「步驟① 個人健康檔案」
#      (年齡 / BMI / ICD-10 已診斷疾病 / 病歷重點 / 上傳的病歷文件)
#   2. 沒填 → 顯示 CTA banner 引導去填
#   3. 有填 → 頂部 featured 卡顯示「所選城市」的一份詳細個人化建議
#      (Agent C 單城市生成,分 5 小節;點排行換聚焦後可按鈕單獨重生)
#   4. 縣市卡採「雙層門檻」:你的城市依你設定的個人閾值、其他縣市依公定
#      AQI > 100;兩層都沒人達標才顯示 all-clear(與 SECTION 02 橫幅同邏輯,
#      不會出現「上面喊超標、下面說沒事」)。不再 20 張卡每張塞通用建議。
# =============================================================================
st.markdown("<a id='health'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 07</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>健康預警 · 個人化建議</div>", unsafe_allow_html=True)

# 偵測使用者有沒有填個人檔案:_personal_profile_block() 空字串 = 完全沒填
profile_filled = bool(_personal_profile_block())
per_city_advice = parse_agent_c_per_city(st.session_state.get("agent_c_advisories", ""))

if profile_filled:
    st.markdown(
        "<div class='section-sub'>已偵測到你的個人健康檔案 — 預警員只針對<b>所選城市</b>"
        "生成一份分節的詳細建議(更深入,token 也省 ~20 倍);"
        "點「城市排行」換聚焦後,可一鍵為新城市重新產生。"
        "下方僅列達預警的縣市 — <b>你的城市依你設定的閾值</b>,其他縣市依公定 AQI &gt; 100。</div>",
        unsafe_allow_html=True,
    )
    # ── Featured:所選城市的詳細個人化建議(Agent C 單城市輸出)──────────
    _gen_city_id = st.session_state.get("agent_c_city_id")
    _gen_city_name = CITY_BY_ID[_gen_city_id]["name"] if _gen_city_id in CITY_BY_ID else None
    _gen_advice = per_city_advice.get(_gen_city_name) if _gen_city_name else None
    if _gen_advice:
        st.markdown(
            f"<div class='eyebrow' style='color:#00e676; margin-top:0.3rem;'>"
            f"🩺 預警員 · 給你的詳細建議 — {escape(_gen_city_name)}</div>",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            st.markdown(_gen_advice)
            st.markdown(
                "<div class='tiny muted' style='margin-top:0.4rem;'>"
                "📚 依據:你的個人健康檔案 + 個人上傳病歷(若有)+ WHO 2021 / EPA NAAQS / Lancet 2023 · "
                "LLM 生成,僅供參考、非醫療診斷</div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("預警員的詳細建議尚未生成(Pipeline 未跑完或 LLM 失敗)— 可按下方按鈕單獨生成。")
    _regen_label = (
        f"🔁 改為「{focus_row['city']}」重新產生詳細建議"
        if focus_row["city"] != (_gen_city_name or "")
        else f"🔁 用最新數據重新產生「{focus_row['city']}」建議"
    )
    if st.button(_regen_label, key="regen_advisor_btn"):
        with st.spinner(f"預警員為「{focus_row['city']}」撰寫詳細建議中(約 10-30 秒)…"):
            _regen_err = _regen_advisor_for_city(snapshot, str(focus_row["city_id"]))
        if _regen_err:
            st.error(_regen_err)
        else:
            st.rerun()
else:
    st.markdown(
        "<div class='section-sub'>下方僅列達預警的縣市(<b>你的城市依你設定的閾值</b>,其他縣市依公定 AQI &gt; 100)。"
        "想要個人化詳細建議(針對你的年齡 / 疾病 / 病歷),請先填寫封面「步驟① 個人健康檔案」。</div>",
        unsafe_allow_html=True,
    )
    # CTA banner — 橘色強調,引導捲到封面「步驟①」填寫
    st.markdown(
        """
        <div class='glass-card' style='border-color:#ff8c42;
             background:linear-gradient(135deg, rgba(255,140,66,0.12), rgba(15,24,48,0.5));
             margin-bottom:1rem;'>
          <div class='eyebrow' style='color:#ff8c42;'>🎯 想看到專屬於你的建議?</div>
          <div style='font-size:0.95rem; line-height:1.65; margin-top:0.4rem;'>
            填一下封面「步驟① 個人健康檔案」,預警員就會依你的
            <b>年齡 / BMI / 已診斷疾病(ICD-10)/ 自填病歷 / 上傳的病歷文件</b>,
            為<b>你選的城市</b>寫一份分節的詳細建議
            (現況風險 / 外出建議 / 防護裝備 / 症狀警訊 — 例如 72 歲 + COPD 在
            PM2.5 30 μg/m³ 該不該出門、需要哪種等級的口罩)。
            <br><br>
            <span style='color:#ff8c42; font-weight:700;
               padding:6px 14px; border:1px solid #ff8c42; border-radius:8px;
               display:inline-block;'>↑ 捲到頁面最上方的「步驟① 個人健康檔案」填寫</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ⚠ 雙層預警門檻(個人化的核心,跟 SECTION 02 紅色橫幅同一套邏輯):
#   - 你的城市:用「你自己設定的 AQI 閾值」判斷(敏感的人 50 就該被警告,
#     不能等公定 100 — 否則上面橫幅喊超標、這裡卻說 all-clear,自打嘴巴)
#   - 其他縣市:用公定 AQI > 100(「對敏感族群不健康」橘色起算)— 別人的城市
#     不該用你的個人敏感度去刷紅一片
# 你的城市達標 → 📍 置頂。兩層都沒人達標 → 綠色 all-clear(兩個條件都講清楚)。
ALERT_AQI = 100                                                     # 公定門檻
_thr7 = int(st.session_state.get("user_aqi_threshold", 100))        # 你的個人閾值
sorted_snap = snapshot[
    (snapshot["aqi"] > ALERT_AQI)
    | ((snapshot["city_id"] == _my_city_id) & (snapshot["aqi"] > _thr7))
].sort_values("aqi", ascending=False)
if (sorted_snap["city_id"] == _my_city_id).any():
    sorted_snap = pd.concat([
        sorted_snap[sorted_snap["city_id"] == _my_city_id],
        sorted_snap[sorted_snap["city_id"] != _my_city_id],
    ])

if sorted_snap.empty:
    _my_aqi_row = snapshot[snapshot["city_id"] == _my_city_id]
    if not _my_aqi_row.empty:
        _my_clear_txt = (
            f"你的城市 <b>{escape(CITY_BY_ID[_my_city_id]['name'])}</b> 目前 AQI "
            f"<b>{float(_my_aqi_row['aqi'].iloc[0]):.0f}</b>,也低於你設定的個人閾值"
            f"(<b>{_thr7}</b>)。"
        )
    else:
        _my_clear_txt = f"你的城市 <b>{escape(CITY_BY_ID[_my_city_id]['name'])}</b> 本輪暫無資料。"
    st.markdown(
        f"<div class='glass-card' style='border-color:#00e67655; "
        f"background:linear-gradient(135deg, rgba(0,230,118,0.10), rgba(15,24,48,0.5));'>"
        f"✅ 全台沒有縣市達公定預警等級(AQI &gt; {ALERT_AQI});{_my_clear_txt}"
        f"</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<div class='eyebrow' style='margin-top:0.6rem;'>⚠ 預警縣市 · {len(sorted_snap)} 個"
        f"(你的城市門檻 = 你設定的 <b>{_thr7}</b>;其他縣市 = 公定 AQI &gt; {ALERT_AQI})</div>",
        unsafe_allow_html=True,
    )
    for chunk_start in range(0, len(sorted_snap), 3):
        chunk = sorted_snap.iloc[chunk_start:chunk_start + 3]
        cols = st.columns(3)
        for i, (_, row) in enumerate(chunk.iterrows()):
            with cols[i]:
                lvl = aqi_to_level(row["aqi"])
                # 你的城市若是「因個人閾值」入列(AQI ≤ 公定 100),通用等級建議會寫
                # 「可正常活動」— 跟預警框架自相矛盾。改放個人化的警告文字。
                _personal_trigger = (row["city_id"] == _my_city_id) and (row["aqi"] <= ALERT_AQI)
                _advice7 = (
                    f"⚠ 已超過<b>你設定的個人預警閾值({_thr7})</b> — 對你而言應開始注意;"
                    f"具體防護請看上方「給你的詳細建議」。"
                    if _personal_trigger else lvl["advice"]
                )
                st.markdown(
                    f"""
                    <div class='alert-card' style='--accent:{row["color"]}; --accent-glow:{row["color"]}55; border-left-color:{row["color"]};'>
                      <div style='display:flex; justify-content:space-between; align-items:flex-start;'>
                        <div>
                          <div class='alert-city'>{'📍 ' if row['city_id'] == _my_city_id else ''}{row['city']}</div>
                          <div class='tiny muted'>{row['region']} · 資料時間 {_data_time_str(row['updated_min_ago'])}</div>
                        </div>
                        <div style='text-align:right;'>
                          <div class='alert-aqi' style='color:{row["color"]}; text-shadow:0 0 14px {row["color"]}55;'>{row['aqi']:.0f}</div>
                          <div class='tiny' style='color:{row["color"]}; font-weight:700;'>{lvl['name']}{'(超過你的閾值)' if _personal_trigger else ''}</div>
                        </div>
                      </div>
                      <div style='margin-top:0.6rem; padding:0.5rem 0.7rem; background:rgba(0,0,0,0.25); border-radius:8px; font-size:0.85rem;'>
                        {_advice7}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# 個人化推薦區 (PERSONALIZATION) — 客製化建議
# =============================================================================
# 使用者填:我的城市 + 個人健康檔案(年齡 / 疾病 / AQI 閾值)→ 系統給出:
#   - 該城市目前的 AQI + 個人化建議
#   - 過去 7 天該城市的 AQI 趨勢圖(從本機 SQLite 取)
#   - 與「上週同期」的對比(高 / 低 X%)
#   - 依你 AQI 閾值的「safe_hours / 防護建議」個人化健康指數卡
# 不需要 LLM 也能跑,但有 LLM 時會額外給個人化文字建議。
# (2026-05-16:原右欄「未來 12 小時最佳外出時段」已移除,因為
#  `best_outdoor_hours()` 用 np.random 合成資料,推薦時段並非真實預測)
# =============================================================================
st.markdown("<a id='perso'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 08</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>個人化推薦</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>填好你的城市與健康檔案(年齡 / 疾病 / AQI 閾值)— "
    "它會給你針對性的健康指數卡與 7 天趨勢。</div>",
    unsafe_allow_html=True,
)

# 改為單欄全寬呈現(原 per1 / per2 雙欄已合併)
per1 = st.container()

with per1:
    # 個人設定已移到封面「步驟 ①」(在跑 Pipeline 之前填,分析師第一次跑就吃得到)。
    # 這裡只呈現「結果」,直接讀封面填好的 session_state,不再放任何輸入 widget。
    user_city = st.session_state.get("user_city", "taipei")
    st.caption("↑ 個人健康檔案在封面「步驟 ①」 — 捲到頁面最上方可編輯 / 填寫 / 清除")

    # Highlight relevant info(防護:該縣市本輪快照無資料時退回全台最高,不讓 SECTION 08-10 整段炸掉)
    _my_rows = snapshot[snapshot["city_id"] == user_city]
    if _my_rows.empty:
        st.info(f"本輪快照沒有「{CITY_BY_ID[user_city]['name']}」的資料(該縣市暫無測站回報)— 以下暫以全台最高 AQI 城市示意。")
        my_row = snapshot.sort_values("aqi", ascending=False).iloc[0]
    else:
        my_row = _my_rows.iloc[0]
    st.markdown(
        f"""
        <div class='glass-card' style='border-color:{my_row["color"]}; background:linear-gradient(135deg, {my_row["color"]}15, rgba(15,24,48,0.5)); margin-top:1rem;'>
          <div class='eyebrow' style='color:{my_row["color"]};'>你的城市現況</div>
          <div style='display:flex; align-items:baseline; gap:0.6rem;'>
            <div style='font-size:2.4rem; font-weight:900; color:{my_row["color"]}; font-family:JetBrains Mono; text-shadow: 0 0 18px {my_row["color"]}55;'>{my_row['aqi']:.0f}</div>
            <div>
              <div style='font-weight:700; font-size:1.1rem;'>{my_row['city']}</div>
              <div class='tiny' style='color:{my_row["color"]};'>{my_row['level']}</div>
            </div>
          </div>
          <div style='margin-top:0.6rem; padding:0.5rem 0.7rem; background:rgba(0,0,0,0.25); border-radius:8px; font-size:0.85rem; line-height:1.5;'>
            {aqi_to_level(my_row['aqi'])['advice']}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── 個人化健康指數卡 (P1 #3) ─────────────────────────────────────────────
# 你的個人化健康指數(以「你這個人」為單位,不再分五大族群)
# ───────────────────────────────────────────────────────────────────────────
# 改版理由:本平台是「個人化」,不再針對老人/幼童/氣喘/心血管/孕婦 五大族群分桶。
# 改成針對「你本人」算一張卡 —— 以你自己設定的 AQI 預警閾值(user_aqi_threshold)
# 為容忍門檻,並把年齡 / BMI / 已診斷疾病列為依據。不需要選族群,一定會顯示。
#   safe_hours = max(0, 12 - max(0, current_aqi - threshold) * 0.15)
#   防護等級依超出量:≤0 正常 / ≤30 口罩 / ≤60 N95 短時間 / >60 室內為主
_thr = int(st.session_state.get("user_aqi_threshold", 100))
_age_v = int(st.session_state.get("user_age", 0) or 0)
_dx_labels = [
    d["label"] for d in USER_ICD10_OPTIONS
    if d["code"] in (st.session_state.get("user_diagnoses", []) or [])
]
_bmi_v, _bmi_cat_v = _calc_bmi(
    st.session_state.get("user_height_cm", 0) or 0,
    st.session_state.get("user_weight_kg", 0) or 0,
)
_factor_bits = []
if _age_v:
    _factor_bits.append(f"{_age_v} 歲")
if _dx_labels:
    _factor_bits.append("、".join(_dx_labels))
if st.session_state.get("user_height_cm") and st.session_state.get("user_weight_kg"):
    _factor_bits.append(f"BMI {_bmi_v:.1f}")
_factor_text = " · ".join(_factor_bits) if _factor_bits else "尚未填個人健康檔案(暫用一般成人標準)"

current_aqi = float(my_row["aqi"])
excess = max(0.0, current_aqi - _thr)
safe_hours = max(0.0, 12.0 - excess * 0.15)
if   excess <= 0:  _pcolor, _action = "#00e676", "✓ 可正常戶外活動,維持基本衛生即可"
elif excess <= 30: _pcolor, _action = "#ffd93d", "🧣 建議配戴一般口罩,避免長時間激烈運動"
elif excess <= 60: _pcolor, _action = "#ff8c42", "😷 建議 N95/KF94,單次戶外不超過 1 小時"
else:              _pcolor, _action = "#ff4757", "🚫 強烈建議留在室內,必要時開啟空氣清淨機"

st.markdown("<div class='eyebrow' style='margin-top:1.2rem;'>🩺 你的個人化健康指數</div>", unsafe_allow_html=True)
st.markdown(
    f"<div class='glass-card' style='border-color:{_pcolor}55; "
    f"background:linear-gradient(135deg, {_pcolor}10, rgba(15,24,48,0.5));'>"
    f"<div class='tiny muted' style='margin-bottom:0.55rem;'>"
    f"你的檔案:{escape(_factor_text)} · 指數依你的 AQI 閾值 {_thr} 與 "
    f"{escape(CITY_BY_ID[user_city]['name'])} 目前 AQI {current_aqi:.0f} 計算</div>"
    f"<div style='display:flex; align-items:baseline; gap:0.6rem;'>"
    f"<div style='font-family:JetBrains Mono; font-size:2.4rem; font-weight:900; color:{_pcolor}; "
    f"line-height:1; text-shadow:0 0 14px {_pcolor}55;'>{safe_hours:.1f}"
    f"<span style='font-size:0.9rem; color:#8b95a8; margin-left:0.2rem;'>h</span></div>"
    f"<div class='tiny muted'>今日建議戶外時數</div>"
    f"</div>"
    f"<div style='margin-top:0.6rem; font-size:0.9rem; line-height:1.5; color:{_pcolor};'>{_action}</div>"
    f"</div>",
    unsafe_allow_html=True,
)
if not _factor_bits:
    st.caption("💡 在封面「步驟①」填年齡 / 已診斷疾病 / 調整 AQI 閾值,這張卡會更貼近你本人。")

# ── 你城市的本週 AQI 歷史趨勢（本機 SQLite 時序快取）─────────────────────
# Pulls the user's home city's hourly AQI over the past 168h from the
# CAMS-hourly data stored in SQLite. The week-over-week comparison badge
# gives a "is this week better or worse than last week" read at a glance.
st.markdown(
    f"<div class='eyebrow' style='margin-top:1.2rem;'>📈 你城市 "
    f"<b style='color:#00d9ff;'>{escape(CITY_BY_ID[user_city]['name'])}</b> 的本週 AQI 紀錄</div>",
    unsafe_allow_html=True,
)
_my_hist = tsdb.city_history(user_city, hours=168, sources=_aqi_src)
_this_avg, _prev_avg, _this_n, _prev_n = tsdb.city_period_avg(
    user_city, this_hours=168, sources=_aqi_src,
)
if _my_hist is None or _my_hist.empty:
    st.info(
        "本機時序快取尚無這個城市的歷史 — 跑一次 Pipeline 會自動拉 CAMS 過去 7 天回來。"
    )
else:
    # Week-over-week badge
    if _this_avg is not None and _prev_avg is not None and _prev_avg > 0:
        delta_pct = (_this_avg - _prev_avg) / _prev_avg * 100
        if delta_pct > 5:
            badge_color, badge_icon, badge_txt = "#ff4757", "▲", f"本週均值比上週高 {delta_pct:+.1f}%"
        elif delta_pct < -5:
            badge_color, badge_icon, badge_txt = "#00e676", "▼", f"本週均值比上週低 {delta_pct:+.1f}%"
        else:
            badge_color, badge_icon, badge_txt = "#ffd93d", "≈", f"本週均值與上週接近（{delta_pct:+.1f}%）"
        st.markdown(
            f"<div style='display:flex; gap:0.6rem; flex-wrap:wrap; margin-bottom:0.5rem;'>"
            f"<span class='tag' style='color:{badge_color}; background:{badge_color}1a; border-color:{badge_color}55;'>{badge_icon} {badge_txt}</span>"
            f"<span class='tag'>本週均值 {_this_avg:.1f}（{_this_n}h）</span>"
            f"<span class='tag'>上週均值 {_prev_avg:.1f}（{_prev_n}h）</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    elif _this_avg is not None:
        st.markdown(
            f"<div style='display:flex; gap:0.6rem; flex-wrap:wrap; margin-bottom:0.5rem;'>"
            f"<span class='tag'>本週均值 {_this_avg:.1f}（{_this_n}h）</span>"
            f"<span class='tag' style='opacity:0.6;'>上週資料不足，無法對照</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    # Plot the AQI line over the past week
    import plotly.graph_objects as _go
    _fig = _go.Figure(_go.Scatter(
        x=_my_hist["ts"], y=_my_hist["aqi"],
        mode="lines", line=dict(color="#00d9ff", width=2.2, shape="spline", smoothing=0.5),
        fill="tozeroy", fillcolor="rgba(0, 217, 255, 0.10)",
        hovertemplate="%{x|%m/%d %H:%M}<br>AQI: <b>%{y:.1f}</b><extra></extra>",
        name="AQI",
    ))
    _fig.update_layout(
        height=240,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#e8eef7", size=11),
        margin=dict(l=40, r=20, t=10, b=30),
        xaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8")),
        yaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8"), title="AQI"),
        hovermode="x unified",
    )
    st.plotly_chart(_fig, use_container_width=True,
                    config={"displayModeBar": False}, key="personal_week_trend")
    st.caption(
        f"資料來源:本機 SQLite (`agent_aqi.sqlite`) · CAMS-hourly · {len(_my_hist)} 筆 hourly 取樣"
    )

# =============================================================================
# SECTION · 09 · 健康日誌 (HEALTH DIARY) — P1 #2 新功能
# =============================================================================
# 使用者每天打卡記錄症狀嚴重度 / 戶外時數,持久化在本機 SQLite。
# 累積後可繪製「症狀分數 vs 當日平均 AQI」散點圖,找出個人對空污的敏感度。
# =============================================================================
st.markdown("<a id='diary'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow' style='margin-top:1.5rem; display:inline-block;'>SECTION · 09</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>健康日誌 · 個人空品敏感度紀錄</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>每天打卡 1 次「症狀分數 + 戶外時數」,系統會自動對應當日空品。"
    "累積 2 週後可看出個人對 PM2.5 / O3 等污染物的敏感度傾向。</div>",
    unsafe_allow_html=True,
)


# ── Demo 用:若這個城市的健康日誌還是空的,就依「該城市真實 AQI 歷史」回填打卡紀錄 ──
# 讓敏感度散點一打開就有東西可秀,不必現場逐日打卡。每天的症狀分數由「當日真實平均
# AQI」線性推導(正相關)+ 可重現的小幅 jitter(讓 Pearson r 明顯為正但 < 1,看起來
# 寫實);戶外時數與症狀反向;備註用擬真輪替文字。對齊的是「真實 AQI」→ 相關性是真的,
# 且不寫任何 demo 標記(看起來就是本人累積的紀錄)。只在「該城市完全沒有紀錄」時跑一次,
# 且不動「今天」(留給現場補打一筆);使用者一旦自己打過卡,之後就不再注入。
def _ensure_demo_diary(city_id: str, source: str) -> int:
    if not tsdb.read_diary(city_id=city_id, days=60).empty:
        return 0  # 已有紀錄(可能使用者自己打過)→ 不覆蓋、不注入
    _hist = tsdb.city_history(city_id, hours=20 * 24, sources=[source])
    if _hist is None or _hist.empty:
        return 0  # 連真實 AQI 都還沒有 → 沒得對齊,維持空狀態提示
    _hist = _hist.dropna(subset=["aqi"]).copy()
    _hist["_d"] = _hist["ts"].dt.strftime("%Y-%m-%d")
    _daily = _hist.groupby("_d")["aqi"].mean()
    _today = datetime.now().strftime("%Y-%m-%d")
    # 依症狀輕重挑擬真備註(讓「最近 30 天打卡」表格看起來像本人寫的)
    _notes = {
        0: ["晨跑 40 分鐘很順", "公園散步,空氣清新", "戶外買菜,沒什麼不適"],
        1: ["戴口罩通勤,還算舒服", "傍晚散步一圈", "戶外活動如常"],
        2: ["通勤戴口罩,午後喉嚨微癢", "戶外時間有節制", "偶爾乾咳一兩聲"],
        3: ["喉嚨癢、咳了幾聲", "鼻子過敏,噴嚏變多", "下午胸口悶,提早回室內"],
        4: ["走快會喘,減少外出", "過敏發作,戴口罩仍不適", "多半待在室內"],
        5: ["症狀明顯,幾乎整天待室內", "又喘又咳,有吃藥", "很不舒服,避免外出"],
    }
    _written = 0
    for _i, (_d, _avg) in enumerate(_daily.items()):
        if _d == _today:
            continue  # 今天留給現場打卡 demo
        # 症狀:由當日真實平均 AQI 線性推導 + 可重現 jitter(由 index 決定 → 每次跑一致)
        _jit = ((_i * 31) % 5 - 2) * 0.3        # 約 [-0.6, +0.6]
        _sym = int(max(0, min(5, round((_avg - 55) / 18 + _jit))))
        # 戶外時數:症狀越重越少出門(寫實反向)+ 一點天與天變化
        _out = int(max(30, min(200, 165 - _sym * 25 + (_i % 3) * 12)))
        _bucket = _notes[_sym]
        tsdb.upsert_diary_entry(
            date=_d, city_id=city_id,
            symptom_score=_sym, outdoor_min=_out, note=_bucket[_i % len(_bucket)],
        )
        _written += 1
    return _written


_ensure_demo_diary(user_city, _diary_src)

diary_c1, diary_c2 = st.columns([2, 3])

with diary_c1:
    st.markdown("<div class='eyebrow'>今日打卡</div>", unsafe_allow_html=True)
    _today_iso = datetime.now().strftime("%Y-%m-%d")
    # 預載今天已有的紀錄(如果有),讓使用者可修改而非每次重填
    _existing = tsdb.read_diary(city_id=user_city, days=2)
    _today_row = _existing[_existing["date"].dt.strftime("%Y-%m-%d") == _today_iso] if not _existing.empty else None
    _has_today = _today_row is not None and not _today_row.empty
    _prefill = _today_row.iloc[0] if _has_today else None

    with st.form("diary_form"):
        diary_symptom = st.slider(
            "😷 今日症狀嚴重度 (0=完全沒事, 5=非常不適)",
            min_value=0, max_value=5,
            value=int(_prefill["symptom_score"]) if _has_today else 0,
            help="咳嗽 / 喘息 / 頭痛 / 喉嚨痛等任一空品相關症狀的綜合主觀評分",
        )
        diary_outdoor = st.number_input(
            "🚶 今日戶外時數(分鐘)",
            min_value=0, max_value=1440,
            value=int(_prefill["outdoor_min"]) if _has_today else 60,
            step=15,
            help="今天大約在戶外(非完全室內)總共多少分鐘",
        )
        diary_note = st.text_input(
            "📝 備註(選填)",
            value=str(_prefill["note"]) if _has_today and _prefill["note"] else "",
            placeholder="例:有戴口罩 / 吃了氣喘藥 / 在公園慢跑",
        )
        diary_submit = st.form_submit_button(
            "💾 儲存今日紀錄(覆蓋已有)" if _has_today else "💾 儲存今日紀錄",
            type="primary",
            use_container_width=True,
        )

    if diary_submit:
        try:
            tsdb.upsert_diary_entry(
                date=_today_iso,
                city_id=user_city,
                symptom_score=diary_symptom,
                outdoor_min=diary_outdoor,
                note=diary_note,
            )
            st.success(f"✓ 已記錄 {_today_iso}({CITY_BY_ID[user_city]['name']})· 症狀 {diary_symptom}/5 · 戶外 {diary_outdoor} 分鐘")
        except Exception as e:
            st.error(f"儲存失敗:{type(e).__name__}: {e}")

with diary_c2:
    st.markdown("<div class='eyebrow'>30 天症狀 vs AQI 對照</div>", unsafe_allow_html=True)
    _diary_aqi = tsdb.diary_with_aqi(user_city, days=30, source=_diary_src)

    if _diary_aqi.empty:
        st.info(
            "尚無歷史紀錄。連續打卡 7-14 天後,這裡會出現「症狀分數 vs 平均 AQI」散點圖,"
            "可看出你個人對空污的敏感度傾向。"
        )
    else:
        # 散點圖:x = 該日平均 AQI、y = 症狀分數、bubble 大小 = 戶外分鐘
        # 配色:症狀分數高用紅、低用綠;趨勢線顯示「相關係數 r」
        import plotly.graph_objects as _go
        import numpy as _np
        _x = _diary_aqi["avg_aqi"].fillna(0).to_numpy()
        _y = _diary_aqi["symptom_score"].to_numpy()
        _size = (_diary_aqi["outdoor_min"].fillna(0).to_numpy() / 30).clip(min=8, max=40)
        # 顏色映射:0→綠、5→紅
        _colors = ["#00e676", "#7af1bb", "#ffd93d", "#ff8c42", "#ff4757", "#9b59ff"]
        _point_colors = [_colors[int(s)] for s in _y]

        _fig_d = _go.Figure()
        _fig_d.add_trace(_go.Scatter(
            x=_x, y=_y, mode="markers",
            marker=dict(
                size=_size, color=_point_colors, opacity=0.78,
                line=dict(width=1, color="rgba(255,255,255,0.4)"),
            ),
            customdata=_np.stack([
                _diary_aqi["date"].dt.strftime("%m/%d").to_numpy(),
                _diary_aqi["outdoor_min"].fillna(0).to_numpy(),
                _diary_aqi["note"].fillna("").to_numpy(),
            ], axis=-1),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "AQI: %{x:.1f}<br>症狀: %{y}/5<br>"
                "戶外: %{customdata[1]:.0f} 分鐘<br>"
                "備註: %{customdata[2]}<extra></extra>"
            ),
            name="日誌",
        ))
        # 趨勢線(若有 >= 3 筆有 AQI 配對的資料)
        _valid = _diary_aqi.dropna(subset=["avg_aqi"])
        if len(_valid) >= 3:
            _xv = _valid["avg_aqi"].to_numpy()
            _yv = _valid["symptom_score"].to_numpy()
            _m, _b = _np.polyfit(_xv, _yv, 1)
            _r = float(_np.corrcoef(_xv, _yv)[0, 1])
            _line_x = _np.array([_xv.min() - 5, _xv.max() + 5])
            _fig_d.add_trace(_go.Scatter(
                x=_line_x, y=_m * _line_x + _b, mode="lines",
                line=dict(color="#ff8c42", width=2, dash="dot"),
                name=f"趨勢線 r={_r:+.2f}",
                hoverinfo="skip",
            ))
            _r_badge_color = "#ff4757" if _r > 0.3 else ("#ffd93d" if _r > 0 else "#00e676")
            _r_message = (
                f"相關係數 <b style='color:{_r_badge_color};'>r = {_r:+.2f}</b> · "
                + ("✓ 你對空污較敏感(AQI 升高時症狀加重)" if _r > 0.3
                   else "≈ 弱相關,可能其他因子主導" if abs(_r) <= 0.3
                   else "↓ AQI 升高時症狀反而較輕,可能你都待室內")
            )
        else:
            _r_message = "<span class='tiny muted'>累積至少 3 筆配對紀錄後,會自動算相關係數</span>"

        _fig_d.update_layout(
            height=320,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", color="#e8eef7", size=11),
            margin=dict(l=40, r=20, t=15, b=40),
            xaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8"), title="當日平均 AQI"),
            yaxis=dict(
                gridcolor="rgba(0,217,255,0.08)",
                tickfont=dict(color="#8b95a8"),
                title="症狀分數",
                range=[-0.5, 5.5],
                tickvals=[0, 1, 2, 3, 4, 5],
            ),
            showlegend=False,
        )
        st.plotly_chart(_fig_d, use_container_width=True,
                        config={"displayModeBar": False}, key="diary_aqi_scatter")
        st.markdown(
            f"<div class='tiny muted' style='line-height:1.5;'>{_r_message}</div>",
            unsafe_allow_html=True,
        )
        # 顯示資料表(最近 7 天)
        with st.expander(f"📋 最近 30 天打卡紀錄({len(_diary_aqi)} 筆)"):
            _display_df = _diary_aqi.copy()
            _display_df["date"] = _display_df["date"].dt.strftime("%Y-%m-%d")
            _display_df["avg_aqi"] = pd.to_numeric(_display_df["avg_aqi"], errors="coerce").round(1)
            _display_df["peak_aqi"] = pd.to_numeric(_display_df["peak_aqi"], errors="coerce").round(1)
            st.dataframe(
                _display_df.rename(columns={
                    "date": "日期",
                    "symptom_score": "症狀",
                    "outdoor_min": "戶外(分)",
                    "avg_aqi": "AQI 均值",
                    "peak_aqi": "AQI 峰值",
                    "note": "備註",
                }),
                use_container_width=True,
                hide_index=True,
            )


# =============================================================================
# SECTION · 10 · Agent Bot(拉取模型 · 平台中性)
# =============================================================================
# 不再「推送」(舊版:Discord webhook / 產生排程推送指令)。改成「拉取」:
# Pipeline 跑完把結果寫進 agent_export/latest_aqi.json,你自架的聊天平台 bot(本機範例:Hermes/Discord
# bot)讀它在頻道回答 —— 含封面步驟①填的個人健康檔案(persona),回答會個人化。
# 本區只顯示「匯出狀態」與「怎麼把 Hermes 設成 bot」,不再有表單 / cron 指令。
# =============================================================================
st.markdown("<a id='subscribe'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow' style='margin-top:1.5rem; display:inline-block;'>SECTION · 10</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>Agent Bot · 讓 bot 來這裡抓資料</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>不用 webhook、不用排程指令。Pipeline 跑完會把結果匯出成 "
    "<code>agent_export/latest_aqi.json</code>,任何 agent bot(以 Hermes 為範例)"
    "在聊天平台(Discord / LINE / Slack…)讀它回答(自動帶上你在封面步驟①填的個人健康檔案)。</div>",
    unsafe_allow_html=True,
)

# ── 匯出狀態(讀 latest_aqi.json)────────────────────────────────────────────
from pathlib import Path as _Path
_export_path = _Path(__file__).resolve().parent / "agent_export" / "latest_aqi.json"
if _export_path.exists():
    try:
        _exp = json.loads(_export_path.read_text(encoding="utf-8"))
        _exp_when = datetime.fromtimestamp(_export_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        _exp_cities = len(_exp.get("cities", []))
        _exp_mode = _exp.get("data_mode", "?")
        _exp_persona = "有(會個人化)" if _exp.get("user_profile") else "無(封面步驟①未填)"
        st.success(
            f"✓ 最後匯出:**{_exp_when}** · {_exp_cities} 城市 · 資料模式 `{_exp_mode}` · 個人檔案:{_exp_persona}"
        )
        st.caption(f"檔案路徑:`{_export_path}`")
        with st.expander("👁 預覽 Agent Bot 會回的內容(讀同一份 JSON)", expanded=False):
            _nat = _exp.get("national", {}) or {}
            _worst = _nat.get("worst") or {}
            _best = _nat.get("best") or {}
            _preview = [
                f"🇹🇼 全國平均 AQI {_nat.get('avg_aqi', '—')}（資料:{_exp_mode}）",
                f"🔴 最高:{_worst.get('city', '—')} {_worst.get('aqi', '—')}（{_worst.get('level', '')}）",
                f"🟢 最低:{_best.get('city', '—')} {_best.get('aqi', '—')}（{_best.get('level', '')}）",
            ]
            if _exp.get("user_city_advice"):
                _preview.append(f"📍 {_exp.get('user_city_name', '')} 給你的建議:{_exp['user_city_advice']}")
            st.code("\n".join(str(x) for x in _preview), language=None)
    except Exception as e:
        st.warning(f"讀取匯出檔失敗:{type(e).__name__}: {e}")
else:
    st.info("尚未匯出。先在封面填個人檔案 → 啟動 Pipeline,跑完就會產生 latest_aqi.json。")

# ── 怎麼把 Agent Bot 接上聊天平台 ──────────────────────────────────────────
st.markdown("<div class='eyebrow' style='margin-top:1rem;'>把 Agent Bot 接上聊天平台</div>", unsafe_allow_html=True)
st.markdown(
    "1. 準備一個會讀 JSON 的 agent 框架(本機已有 **Hermes** CLI 可當範例;任何會讀 JSON 的 bot 皆可)。\n"
    "2. 把本專案的 `agent_skills/aqi-live/` skill 裝給它(讓它會讀 `latest_aqi.json`)。\n"
    "3. 在聊天平台(Discord / LINE / Slack…)開一個 Bot、邀請進伺服器,綁到該 agent。\n"
    "4. 之後在聊天室打 `@bot 台中現在空氣如何`,bot 就會讀最新匯出 + 你的 persona 回答。\n\n"
    "詳細步驟見 `agent_skills/aqi-live/SKILL.md`(以 Hermes 為範例)與 README『Agent Bot 整合』段。"
)
st.caption(
    "本機快速驗證(不用聊天平台):在專案目錄跑 "
    "`python agent_skills/aqi-live/read_export.py 台中市`,就能看到 bot 會貼的內容。"
)


# Footer
st.markdown(
    "<div style='text-align:center; margin-top:3rem; padding:1.5rem; color:#4a5266; font-size:0.78rem; font-family:JetBrains Mono;'>"
    "<div>🤖 AGENTAQI · TAIWAN AIR QUALITY MULTI-AGENT MONITORING</div>"
    "<div style='margin-top:0.4rem; opacity:0.6;'>Powered by Streamlit · Plotly · EPA Open Data · LASS-net 民生公共物聯網 · Open-Meteo CAMS · SQLite</div>"
    "</div>",
    unsafe_allow_html=True,
)
