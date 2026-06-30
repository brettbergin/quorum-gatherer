"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ agents
class AgentInfo(BaseModel):
    key: str
    name: str
    role: str
    phase: str
    order: int
    default_provider: str
    default_model: str
    owned_sections: list[str]


# ------------------------------------------------------------------ providers / settings
class ReasoningSpecOut(BaseModel):
    """Shape of a provider's raw reasoning knob, so clients can render the right control."""

    kind: str  # "effort" | "thinking_budget" | "none"
    settings_key: str
    efforts: list[str]
    budget_min: int
    budget_max: int
    budget_default: int
    model_pattern: str  # regex; which catalog model ids expose the knob


class ProviderSpecOut(BaseModel):
    key: str
    label: str
    default_model: str
    suggested_models: list[str]
    reasoning: ReasoningSpecOut


class ProviderSettingOut(BaseModel):
    provider: str
    default_model: str | None  # council-member model
    reasoning: str | None
    chairman_model: str | None
    chairman_reasoning: str | None
    is_enabled: bool
    has_key: bool


class ProviderSettingIn(BaseModel):
    provider: str
    api_key: str | None = None  # None = leave unchanged, "" = clear
    default_model: str | None = None
    reasoning: str | None = None
    chairman_model: str | None = None
    chairman_reasoning: str | None = None
    is_enabled: bool = True


class ProviderApplyIn(BaseModel):
    """Validate a provider key (real test call) and, on success, save + enable it."""

    provider: str
    api_key: str | None = None  # blank = reuse the stored key
    default_model: str | None = None  # council-member model
    reasoning: str | None = None
    chairman_model: str | None = None
    chairman_reasoning: str | None = None


class ProviderModelsIn(BaseModel):
    """Fetch a provider's live model catalog (also validates the key)."""

    provider: str
    api_key: str | None = None  # blank = reuse the stored key


class ModelInfoOut(BaseModel):
    id: str
    label: str
    supports_reasoning: bool


class ModelCatalogOut(BaseModel):
    models: list[ModelInfoOut]


class ProviderRef(BaseModel):
    provider: str


class SettingsOut(BaseModel):
    providers: list[ProviderSpecOut]
    settings: list[ProviderSettingOut]


# ------------------------------------------------------------------ chats
class ChatCreate(BaseModel):
    title: str | None = None
    idea: str | None = None


class ChatOut(ORMModel):
    id: str
    title: str | None
    idea: str | None
    status: str
    created_at: datetime


class DocumentOut(ORMModel):
    id: str
    filename: str
    content_type: str | None
    created_at: datetime


class AgentRunOut(ORMModel):
    id: str
    agent_key: str
    agent_name: str
    phase: str
    status: str
    provider: str | None
    model: str | None
    output_text: str | None
    output: dict[str, Any] | None
    error: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    created_at: datetime


class MessageOut(ORMModel):
    id: str
    author_type: str
    author_key: str | None
    content: str
    created_at: datetime


class ReportOut(ORMModel):
    content: dict[str, Any]
    markdown: str | None
    created_at: datetime


class ChatDetail(ChatOut):
    documents: list[DocumentOut] = Field(default_factory=list)
    agent_runs: list[AgentRunOut] = Field(default_factory=list)
    messages: list[MessageOut] = Field(default_factory=list)
    report: ReportOut | None = None


class SubmitItem(BaseModel):
    idea: str
