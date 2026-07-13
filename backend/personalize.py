"""個人設定模型。

公開前端使用非敏感的城市、活動、敏感程度與提醒門檻；舊的健康欄位只保留給受信任的
相容流程。這讓 Agent 可以個人化，又不必要求使用者把病歷或 LLM 金鑰放進瀏覽器。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import data  # 專案根的 data.py（USER_ICD10_OPTIONS 等）

_SEX_LABEL = {"female": "女", "male": "男", "other": "其他", "prefer_not": "未提供"}
_SENSITIVITY_LABEL = {"general": "一般", "sensitive": "較敏感"}
_ACTIVITY_LABEL = {
    "commute": "通勤", "walk": "散步", "run": "跑步", "cycle": "單車", "outdoor": "戶外工作",
}


@dataclass
class UserProfile:
    age: int = 0
    sex: str = "prefer_not"          # female / male / other / prefer_not
    height_cm: float = 0.0
    weight_kg: float = 0.0
    diagnoses: list[str] = field(default_factory=list)   # ICD-10 code 字串
    med_history: str = ""
    city: str = "taipei"
    threshold: int = 100
    preferences_enabled: bool = False
    sensitivity: str = "general"
    activity: str = "commute"

    @classmethod
    def from_dict(cls, d: dict | None) -> "UserProfile":
        d = d or {}
        return cls(
            age=int(d.get("age") or 0),
            sex=str(d.get("sex") or "prefer_not"),
            height_cm=float(d.get("height_cm") or 0),
            weight_kg=float(d.get("weight_kg") or 0),
            diagnoses=list(d.get("diagnoses") or []),
            med_history=str(d.get("med_history") or "").strip(),
            city=str(d.get("city") or "taipei"),
            threshold=int(d.get("threshold") or 100),
            preferences_enabled=bool(d.get("preferences_enabled", False)),
            sensitivity=(str(d.get("sensitivity") or "general")
                         if str(d.get("sensitivity") or "general") in _SENSITIVITY_LABEL else "general"),
            activity=(str(d.get("activity") or "commute")
                      if str(d.get("activity") or "commute") in _ACTIVITY_LABEL else "commute"),
        )

    @property
    def has_health_profile(self) -> bool:
        return bool(self.age or self.diagnoses or self.med_history)

    @property
    def is_filled(self) -> bool:
        """有舊健康檔案，或前端明確啟用非敏感偏好，就可產生個人化建議。"""
        return self.has_health_profile or self.preferences_enabled


def calc_bmi(height_cm: float, weight_kg: float) -> tuple[float, str]:
    """(BMI, 中文分類)。height<=0 回 (0.0, "—")。分類依 WHO 通用版。"""
    if height_cm <= 0:
        return 0.0, "—"
    h_m = height_cm / 100.0
    bmi = weight_kg / (h_m * h_m)
    if bmi < 18.5:
        cat = "過輕"
    elif bmi < 24:
        cat = "正常"
    elif bmi < 27:
        cat = "過重"
    elif bmi < 30:
        cat = "輕度肥胖"
    elif bmi < 35:
        cat = "中度肥胖"
    else:
        cat = "重度肥胖"
    return bmi, cat


def _diag_labels(codes: list[str], with_code: bool = True) -> list[str]:
    out = []
    for d in data.USER_ICD10_OPTIONS:
        if d["code"] in codes:
            out.append(f"{d['label']}（{d['code']}）" if with_code else d["label"])
    return out


def persona_dict(p: UserProfile) -> dict | None:
    """結構化 dict（供 JSON 匯出 / build_agent_payload 的 user_profile）。沒填回 None。"""
    if not p.is_filled:
        return None
    base = {
        "city": p.city,
        "threshold": int(p.threshold),
        "sensitivity": _SENSITIVITY_LABEL.get(p.sensitivity, "一般"),
        "activity": _ACTIVITY_LABEL.get(p.activity, "通勤"),
    }
    if not p.has_health_profile:
        return base
    bmi, bmi_cat = calc_bmi(p.height_cm, p.weight_kg)
    return {
        **base,
        "age": p.age,
        "sex": _SEX_LABEL.get(p.sex, "未提供"),
        "bmi": round(bmi, 1),
        "bmi_category": bmi_cat,
        "diagnoses": _diag_labels(p.diagnoses),
        "med_history": p.med_history,
    }


def profile_block(p: UserProfile) -> str:
    """給 LLM 的個人設定段落；沒有任何可用設定時回空字串。"""
    if not p.is_filled:
        return ""
    bmi, bmi_cat = calc_bmi(p.height_cm, p.weight_kg)
    diag_text = "、".join(
        f"{d['label']}({d['code']})"
        for d in data.USER_ICD10_OPTIONS if d["code"] in p.diagnoses
    ) or "無"
    sex_label = _SEX_LABEL.get(p.sex, "未提供")
    age_txt = f"{p.age} 歲" if p.age else "未提供"
    thr = int(p.threshold)
    preference_lines = (
        "=== 使用者非敏感空氣偏好（請在回答中明確參考）===\n"
        f"空氣敏感程度：{_SENSITIVITY_LABEL.get(p.sensitivity, '一般')}\n"
        f"主要活動：{_ACTIVITY_LABEL.get(p.activity, '通勤')}\n"
        f"自設 AQI 預警閾值：{thr}\n"
    )
    if not p.has_health_profile:
        return (
            preference_lines
            + "請依敏感程度、活動強度與門檻給具體建議；不得推測使用者有任何疾病或病史。\n"
        )
    return (
        preference_lines
        + "=== 使用者健康檔案（受信任相容流程）===\n"
        f"年齡：{age_txt} / 性別：{sex_label} / BMI：{bmi:.1f}（{bmi_cat}）\n"
        f"已診斷疾病：{diag_text}\n"
        f"病歷重點：{p.med_history or '（未填）'}\n"
        "請在建議中明確參考已提供的健康因素，不得擴張或推測未提供的病況。\n"
    )
