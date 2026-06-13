"""One-shot repair: rebuild daily_note config.yaml from the last VALID backup and
(re)bind aqi-reporter to the Discord channel — with a SHORT channel prompt.

歷史教訓(兩次損壞,2026-06-10 00:14 與 01:04):把 1900+ 字的完整 persona 內嵌進
`discord.channel_prompts`,會被 Hermes 自己的 config writer 在後續任何寫入時
重新序列化弄壞(長 quoted scalar 行黏合 → 整份 config 解析失敗、退回 fallback)。
根治:channel_prompt 只放 ~300 字的精簡指令,完整人設/規則留在已安裝的
aqi-live skill(SKILL.md)與 repo 的 agent_personas/aqi-reporter/ 文件。

Usage: 先 `hermes gateway stop`,跑本腳本,再 `hermes gateway start`。
"""
import sys, shutil, yaml
from pathlib import Path

PROFILE = Path(r"C:\Users\tunai\AppData\Local\hermes\profiles\daily_note")
VALID   = PROFILE / "config.yaml.bak-agentaqi-bind-20260609-223106"   # 最新可解析基底
CUR     = PROFILE / "config.yaml"

TARGET = "1492132439471030272"   # #每日空氣天氣報告

SHORT_PROMPT = (
    "你是 AgentAQI 的空品播報員(aqi-reporter)。回答空品問題:讀環境變數 AGENTAQI_EXPORT "
    "指向的 latest_aqi.json(或執行已安裝 skill aqi-live 的 read_export.py),只引用該 JSON "
    "的數值、絕不編造;data_mode 非 real 開頭標「(模擬/demo 資料)」;有 user_profile 就附"
    "個人化提醒(年齡/診斷/BMI),該城市 AQI 超過 threshold 要標「已超過你設定的個人預警閾值」;"
    "繁體中文、3-6 行、先數字後建議;查無資料就明說。詳細規則見 aqi-live 的 SKILL.md。"
)

cfg = yaml.safe_load(VALID.read_text(encoding="utf-8"))
disc = cfg.get("discord")
if not isinstance(disc, dict):
    sys.exit("！valid backup has no discord: section")

disc["channel_prompts"] = {TARGET: SHORT_PROMPT}
disc["channel_skill_bindings"] = [{"id": TARGET, "skills": ["aqi-live"]}]

dumped = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, width=10**9)

# hard guarantee: the emitted YAML parses back to the exact same object
assert yaml.safe_load(dumped) == cfg, "round-trip mismatch — refusing to write"

shutil.copy2(CUR, str(CUR) + ".bak-before-rebind")
CUR.write_text(dumped, encoding="utf-8")

print("OK config.yaml rebuilt (short prompt, round-trip verified)")
print("  channel_prompts        :", list(disc["channel_prompts"].keys()))
print("  channel_skill_bindings :", [(b["id"], b["skills"]) for b in disc["channel_skill_bindings"]])
print("  prompt length (chars)  :", len(SHORT_PROMPT))
