from __future__ import annotations

from functools import lru_cache

from app.core.session import session_manager, SessionManager
from app.llm.provider import LLMProvider
from app.llm.factory import (
    create_router_provider,
    create_clarify_provider,
    create_answer_provider,
    create_fallback_provider,
)


@lru_cache()
def _get_router_provider() -> LLMProvider:
    return create_router_provider()


@lru_cache()
def _get_clarify_provider() -> LLMProvider:
    return create_clarify_provider()


@lru_cache()
def _get_answer_provider() -> LLMProvider:
    return create_answer_provider()


@lru_cache()
def _get_fallback_provider() -> LLMProvider:
    return create_fallback_provider()


def get_session_manager() -> SessionManager:
    return session_manager


def get_llm_provider(scene: str) -> LLMProvider:
    providers = {
        "router": _get_router_provider,
        "clarify": _get_clarify_provider,
        "answer": _get_answer_provider,
        "fallback": _get_fallback_provider,
    }
    factory = providers.get(scene, _get_answer_provider)
    return factory()


def reset_providers():
    """Clear cached providers (useful for testing or config reload)."""
    _get_router_provider.cache_clear()
    _get_clarify_provider.cache_clear()
    _get_answer_provider.cache_clear()
    _get_fallback_provider.cache_clear()
