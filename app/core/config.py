import os
import re
from pathlib import Path
from functools import lru_cache

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 自动加载项目根目录的 .env 文件
ENV_FILE = Path(__file__).parent.parent.parent / ".env"
load_dotenv(ENV_FILE)

CONFIG_DIR = Path(__file__).parent.parent.parent / "configs"


def _resolve_env(value: str) -> str:
    """Resolve ${VAR:default} patterns in config values."""
    pattern = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")

    def replacer(m: re.Match) -> str:
        var = m.group(1)
        default = m.group(2) if m.group(2) is not None else ""
        return os.environ.get(var, default)

    if isinstance(value, str):
        return pattern.sub(replacer, value)
    return value


def _resolve_env_recursive(obj):
    if isinstance(obj, dict):
        return {k: _resolve_env_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_recursive(v) for v in obj]
    if isinstance(obj, str):
        return _resolve_env(obj)
    return obj


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _resolve_env_recursive(raw)


# ── Config Models ──────────────────────────────────────────────


class ProviderConfig(BaseModel):
    model: str
    api_key: str
    base_url: str = ""
    timeout: int = 15
    max_retries: int = 3


class RoutingConfig(BaseModel):
    router: str = "openai"
    clarify: str = "openai"
    answer: str = "claude"
    fallback: str = "qwen"


class ModelConfig(BaseModel):
    default_provider: str = "openai"
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)


class AgentSettings(BaseModel):
    max_clarify_rounds: int = 2
    clarify_confidence_threshold: float = 0.6
    max_tool_call_rounds: int = 5
    llm_timeout: int = 15


class ConcurrencySettings(BaseModel):
    max_concurrent_llm_calls: int = 10
    request_queue_max_size: int = 100


class SessionSettings(BaseModel):
    ttl_seconds: int = 3600
    redis_url: str = "redis://localhost:6379/0"


class CircuitBreakerSettings(BaseModel):
    failure_threshold: int = 5
    cooldown_seconds: int = 60
    half_open_max_calls: int = 1


class RetrySettings(BaseModel):
    llm_max_retries: int = 3
    llm_base_delay: float = 1.0
    tool_max_retries: int = 3
    tool_delay: float = 1.0


class ObservabilitySettings(BaseModel):
    log_level: str = "INFO"
    log_format: str = "json"
    langsmith_enabled: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "scs-agent"


class AppSettings(BaseModel):
    name: str = "SCS-Agent"
    version: str = "1.0.0"
    mode: str = "demo"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class AuthSettings(BaseModel):
    secret: str = "local-demo-secret-change-me"
    token_ttl_seconds: int = 2592000
    cookie_secure: bool = False


class AppConfig(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    concurrency: ConcurrencySettings = Field(default_factory=ConcurrencySettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    circuit_breaker: CircuitBreakerSettings = Field(default_factory=CircuitBreakerSettings)
    retry: RetrySettings = Field(default_factory=RetrySettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


class ToolItemConfig(BaseModel):
    enabled: bool = True
    timeout: int = 5
    base_url: str = ""
    queue_name: str = ""
    fallback_message: str = ""


class ToolConfig(BaseModel):
    tools: dict[str, ToolItemConfig] = Field(default_factory=dict)


class IndexEmbeddingConfig(BaseModel):
    model: str = ""
    dimension: int = 384


class ChromaDBConfig(BaseModel):
    persist_directory: str = "./chroma_data"
    collection_name: str = "scs_knowledge_base"


class RetrievalConfig(BaseModel):
    vector_top_k: int = 20
    bm25_top_k: int = 10
    rerank_top_k: int = 5
    similarity_threshold: float = 0.5


class HotReloadConfig(BaseModel):
    enabled: bool = True
    watch_interval_seconds: int = 30


class IndexConfig(BaseModel):
    embedding: IndexEmbeddingConfig = Field(default_factory=IndexEmbeddingConfig)
    chromadb: ChromaDBConfig = Field(default_factory=ChromaDBConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    domains: list[str] = Field(default_factory=list)
    hot_reload: HotReloadConfig = Field(default_factory=HotReloadConfig)


# ── Cached loaders ─────────────────────────────────────────────


@lru_cache()
def get_model_config() -> ModelConfig:
    data = load_yaml("model_config.yaml")
    return ModelConfig(**data)


@lru_cache()
def get_app_config() -> AppConfig:
    data = load_yaml("app_config.yaml")
    return AppConfig(**data)


@lru_cache()
def get_tool_config() -> ToolConfig:
    data = load_yaml("tool_config.yaml")
    return ToolConfig(**data)


@lru_cache()
def get_index_config() -> IndexConfig:
    from pathlib import Path as _Path
    idx_path = _Path(__file__).parent.parent.parent / "knowledge_base" / "index_config.yaml"
    with open(idx_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    raw = _resolve_env_recursive(raw)
    return IndexConfig(**raw)
