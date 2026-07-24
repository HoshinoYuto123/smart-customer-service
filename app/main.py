from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse

from app.api.middleware import TraceMiddleware
from app.api.routes import router as api_router
from app.api.websocket import router as ws_router
from app.api.support import agent_router, router as support_router
from app.core.config import get_app_config
from app.core.observability import get_logger
from app.core.observability import get_trace_id
from app.support.models import ServiceError

logger = get_logger(__name__)
CHAT_UI_URL = "/static/chat.html?v=20260722-phase3"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up providers and knowledge base on startup."""
    app_config = get_app_config()
    if app_config.app.mode == "production" and app_config.auth.secret == "local-demo-secret-change-me":
        raise RuntimeError("AUTH_SECRET must be configured in production")
    logger.info("app.starting", version=app_config.app.version, mode=app_config.app.mode)

    # Import all tool modules to register them
    try:
        import app.tools  # noqa: F401
        from app.tools.registry import tool_registry
        logger.info("tools.loaded", count=len(tool_registry.list_names()))
    except Exception as e:
        logger.warning("tools.load_failed", error=str(e))

    # Pre-warm LLM providers
    try:
        from app.core.di import get_llm_provider
        get_llm_provider("router")
        get_llm_provider("answer")
        logger.info("providers.warmed")
    except Exception as e:
        logger.warning("providers.warmup_failed", error=str(e))

    # Pre-load knowledge base
    try:
        from app.rag.knowledge_base import knowledge_base_manager
        knowledge_base_manager.load_all_domains()
        index_count = await knowledge_base_manager.ensure_index()
        logger.info("knowledge_base.loaded", index_count=index_count)
    except Exception as e:
        logger.warning("knowledge_base.load_failed", error=str(e))

    yield

    logger.info("app.shutting_down")


def create_app() -> FastAPI:
    config = get_app_config()

    app = FastAPI(
        title=config.app.name,
        version=config.app.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.exception_handler(ServiceError)
    async def support_error_handler(request, exc: ServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                },
                "trace_id": get_trace_id(),
            },
        )

    # Middleware
    app.add_middleware(TraceMiddleware)

    # Static files
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Root redirect to chat UI
    @app.get("/")
    async def root():
        return RedirectResponse(url=CHAT_UI_URL)

    @app.middleware("http")
    async def prevent_stale_chat_ui(request, call_next):
        """Always serve the current chat shell instead of a cached deployment."""
        response = await call_next(request)
        if request.url.path in {"/static/chat.html", "/static/agent.html"}:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Routes
    app.include_router(api_router)
    app.include_router(ws_router)
    app.include_router(support_router)
    app.include_router(agent_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = get_app_config()
    uvicorn.run(
        "app.main:app",
        host=config.app.host,
        port=config.app.port,
        reload=config.app.debug,
        log_level=config.observability.log_level.lower(),
    )
