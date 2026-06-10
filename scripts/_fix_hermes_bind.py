"""One-shot repair: rebuild daily_note config.yaml from the last VALID backup and
(re)bind aqi-reporter to the two Discord channels — using a real YAML emitter so the
persona never breaks the quoting again (the prior hand-serialized writes did).

Safe by construction:
  - base = last parseable config (config.yaml.bak-agentaqi-bind-...), which already
    holds the known-good aqi-reporter persona string (bound to the "aqi" channel).
  - reuse that EXACT persona string for the target channel (no re-concatenation).
  - round-trip assert: yaml.safe_load(safe_dump(cfg)) == cfg  → zero semantic drift.
  - backs up whatever is currently at config.yaml before writing.
"""
import sys, shutil, yaml
from pathlib import Path

PROFILE = Path(r"C:\Users\tunai\AppData\Local\hermes\profiles\daily_note")
VALID   = PROFILE / "config.yaml.bak-agentaqi-bind-20260609-223106"
CUR     = PROFILE / "config.yaml"

TARGET   = "1492132439471030272"   # 每日空氣天氣報告  (user's chosen channel)
SOURCE   = "1503643515391840437"   # aqi              (where the known-good persona lives)

cfg = yaml.safe_load(VALID.read_text(encoding="utf-8"))
disc = cfg.get("discord")
if not isinstance(disc, dict):
    sys.exit("！valid backup has no discord: section")

cp = disc.get("channel_prompts") or {}
if SOURCE not in cp:
    sys.exit(f"！valid backup has no channel_prompts[{SOURCE}] persona to reuse")
persona = cp[SOURCE]                                       # known-good persona string
# User chose: bind ONLY 每日空氣天氣報告 → drop the old `aqi` binding entirely.
disc["channel_prompts"] = {TARGET: persona}
disc["channel_skill_bindings"] = [{"id": TARGET, "skills": ["aqi-live"]}]

dumped = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, width=10**9)

# hard guarantee: the emitted YAML parses back to the exact same object
assert yaml.safe_load(dumped) == cfg, "round-trip mismatch — refusing to write"

shutil.copy2(CUR, str(CUR) + ".corrupt-before-claude-fix")
CUR.write_text(dumped, encoding="utf-8")

print("✓ config.yaml rebuilt and round-trip-verified")
print("  channel_prompts        :", list(disc["channel_prompts"].keys()))
print("  channel_skill_bindings :", [(b["id"], b["skills"]) for b in disc["channel_skill_bindings"]])
print("  persona length (chars) :", len(persona))
print("  backup of old (corrupt):", CUR.name + ".corrupt-before-claude-fix")
