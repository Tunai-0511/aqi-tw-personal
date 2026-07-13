"""FastAPI 請求 / 回應的 pydantic 模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    age: int = Field(default=0, ge=0, le=120)
    sex: Literal["female", "male", "other", "prefer_not"] = "prefer_not"
    height_cm: float = Field(default=0.0, ge=0, le=250)
    weight_kg: float = Field(default=0.0, ge=0, le=500)
    diagnoses: list[str] = Field(default_factory=list, max_length=30)
    med_history: str = Field(default="", max_length=2000)
    city: str = Field(default="taipei", min_length=1, max_length=40)
    threshold: int = Field(default=100, ge=0, le=500)
    # 公開前端只傳非敏感偏好，不要求病歷或疾病資料。
    preferences_enabled: bool = False
    sensitivity: Literal["general", "sensitive"] = "general"
    activity: Literal["commute", "walk", "run", "cycle", "outdoor"] = "commute"


class LLMOverride(BaseModel):
    """使用者自帶金鑰（BYO key）：前端 sidebar 填的 LLM 設定，逐請求覆蓋伺服器預設。
    金鑰只從使用者瀏覽器 → 使用者的後端，走 HTTPS，不落地、不共享。"""
    provider: str | None = None
    key: str | None = None
    model: str | None = None
    base_url: str | None = None


class PipelineRequest(BaseModel):
    profile: ProfileIn | None = None
    city: str | None = Field(default=None, max_length=40)
    llm: LLMOverride | None = None


class AdvisorRequest(BaseModel):
    city: str = Field(min_length=1, max_length=40)
    profile: ProfileIn | None = None
    llm: LLMOverride | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    profile: ProfileIn | None = None
    llm: LLMOverride | None = None
