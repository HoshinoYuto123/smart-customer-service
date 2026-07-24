"""Deterministic support policy shared by Agent and HTTP services.

PRD: CS-BR-005, CS-BR-008 through CS-BR-011, CS-BR-020.
"""

from __future__ import annotations

import re


HUMAN_TERMS = ("转人工", "我要人工", "人工客服", "找人工", "真人客服", "人工处理", "客服人员")
HIGH_RISK_TERMS = (
    "重复扣款",
    "非本人支付",
    "账号被盗",
    "账户被盗",
    "验证码泄露",
    "资金安全",
    "隐私泄露",
    "退款失败",
    "我要投诉",
    "我要申诉",
)
UNRESOLVED_TERMS = ("未解决", "没解决", "没有解决", "还是不行", "没有用", "答非所问", "重复回答")

_SECRET_PATTERNS = (
    re.compile(r"(?i)(密码|password)\s*[:：=]\s*\S+"),
    re.compile(r"(?i)(验证码|verification\s*code|otp)\s*[:：=]?\s*\d{4,8}"),
    re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
)


def requests_human(text: str) -> bool:
    return any(term in text for term in HUMAN_TERMS)


def is_high_risk(text: str) -> bool:
    return any(term in text for term in HIGH_RISK_TERMS)


def reports_unresolved(text: str) -> bool:
    return any(term in text for term in UNRESOLVED_TERMS)


def sanitize_user_text(text: str) -> tuple[str, bool]:
    sanitized = text.strip()
    changed = False
    for pattern in _SECRET_PATTERNS:
        updated = pattern.sub("[敏感信息已隐藏]", sanitized)
        changed = changed or updated != sanitized
        sanitized = updated
    return sanitized, changed


def summarize_for_handoff(text: str, *, max_length: int = 180) -> str:
    sanitized, _ = sanitize_user_text(text)
    compact = re.sub(r"\s+", " ", sanitized).strip()
    return compact[:max_length]


def transfer_reason(text: str, *, unresolved_count: int = 0) -> str:
    if is_high_risk(text):
        return "high_risk"
    if requests_human(text):
        return "explicit_request"
    if unresolved_count >= 2:
        return "repeated_unresolved"
    return ""
