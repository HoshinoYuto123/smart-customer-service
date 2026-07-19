from __future__ import annotations

from app.core.config import get_model_config, ModelConfig
from app.llm.provider import LLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.llm.claude_provider import ClaudeProvider
from app.llm.qwen_provider import QwenProvider
from app.llm.mock_provider import MockProvider
from app.llm.resilient_provider import ResilientLLMProvider


_PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "deepseek": OpenAIProvider,  # DeepSeek 兼容 OpenAI API
    "claude": ClaudeProvider,
    "qwen": QwenProvider,
    "mock": MockProvider,
}


def create_provider(provider_name: str, config: ModelConfig | None = None) -> LLMProvider:
    """Create an LLM provider by name."""
    if config is None:
        config = get_model_config()

    if provider_name not in config.providers:
        raise ValueError(f"Unknown provider: {provider_name}. Available: {list(config.providers.keys())}")

    provider_config = config.providers[provider_name]
    cls = _PROVIDER_CLASSES.get(provider_name, MockProvider)

    provider = cls(
        model=provider_config.model,
        api_key=provider_config.api_key,
        base_url=provider_config.base_url,
        timeout=provider_config.timeout,
        max_retries=provider_config.max_retries,
    )
    return ResilientLLMProvider(provider)


def create_provider_for_scene(scene: str, config: ModelConfig | None = None) -> LLMProvider:
    """Create an LLM provider for a specific scene (router, clarify, answer, fallback)."""
    if config is None:
        config = get_model_config()

    routing = config.routing
    provider_name = getattr(routing, scene, config.default_provider)
    return create_provider(provider_name, config)


def create_router_provider(config: ModelConfig | None = None) -> LLMProvider:
    return create_provider_for_scene("router", config)


def create_clarify_provider(config: ModelConfig | None = None) -> LLMProvider:
    return create_provider_for_scene("clarify", config)


def create_answer_provider(config: ModelConfig | None = None) -> LLMProvider:
    return create_provider_for_scene("answer", config)


def create_fallback_provider(config: ModelConfig | None = None) -> LLMProvider:
    return create_provider_for_scene("fallback", config)
