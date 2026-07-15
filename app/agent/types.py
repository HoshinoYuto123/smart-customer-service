from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Multimedia ──────────────────────────────────────────────────


class MultimediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    CARD = "card"


class MultimediaItem(BaseModel):
    type: MultimediaType
    url: str = ""
    title: str = ""
    description: str = ""
    thumbnail: str = ""


class QuickReply(BaseModel):
    label: str
    value: str
    action: str = ""


# ── Clarify ─────────────────────────────────────────────────────


class ClarifyResult(BaseModel):
    need_clarify: bool
    clarify_type: Literal["scope", "options", "supplement"] = "scope"
    clarify_message: str = ""
    options: list[str] | None = None
    missing_fields: list[str] | None = None
    confidence: float = 0.0


# ── Router ──────────────────────────────────────────────────────


class RouteDecision(BaseModel):
    domain: str = ""
    sub_intent: str = ""
    confidence: float = 0.0
    suggested_tools: list[str] = Field(default_factory=list)
    reasoning: str = ""
    layer1_result: str = ""
    layer2_candidates: list[dict] = Field(default_factory=list)


# ── Tool ────────────────────────────────────────────────────────


class ToolResult(BaseModel):
    tool_name: str = ""
    success: bool = True
    data: dict = Field(default_factory=dict)
    error_message: str = ""
    latency_ms: float = 0.0


# ── FAQ ─────────────────────────────────────────────────────────


class FAQItem(BaseModel):
    id: str
    domain: str
    question: str
    answer: str
    answer_multimedia: list[MultimediaItem] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    related_faqs: list[str] = Field(default_factory=list)
    version: int = 1
    status: Literal["active", "draft", "archived"] = "active"


# ── Response ────────────────────────────────────────────────────


class AgentResponse(BaseModel):
    text: str
    multimedia: list[MultimediaItem] = Field(default_factory=list)
    quick_replies: list[QuickReply] = Field(default_factory=list)
    action: Literal["reply", "clarify", "transfer_human", "create_ticket"] | None = "reply"
    metadata: dict = Field(default_factory=dict)


# ── API Models ──────────────────────────────────────────────────


class ChatRequest(BaseModel):
    session_id: str
    message: str
    context: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    response: AgentResponse


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    providers: list[str] = Field(default_factory=list)


# ── LLM ─────────────────────────────────────────────────────────


class LLMResponse(BaseModel):
    content: str
    model: str = ""
    tokens_used: int = 0
    tool_calls: list[dict] = Field(default_factory=list)
    finish_reason: str = "stop"
    latency_ms: float = 0.0


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str = ""
    tool_call_id: str = ""
    tool_calls: list[dict] = Field(default_factory=list)


class ToolDef(BaseModel):
    name: str
    description: str
    parameters: dict = Field(default_factory=dict)


# ── Session ─────────────────────────────────────────────────────


class SessionContext(BaseModel):
    session_id: str
    user_id: str = ""
    channel: str = "web"
    clarify_count: int = 0
    current_domain: str = ""
    history: list[dict] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
