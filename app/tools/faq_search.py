"""FAQ search tool – queries the hybrid retriever over the knowledge base."""

from app.agent.types import ToolResult
from app.tools.registry import tool_registry


@tool_registry.register(
    name="faq_search",
    domain="global",
    description="在FAQ知识库中搜索相关问题和答案，支持按业务域过滤",
    params_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询关键词或问题"},
            "domain": {
                "type": "string",
                "description": "可选业务域过滤（如 account, order, product），不填则全局搜索",
            },
        },
        "required": ["query"],
    },
)
async def faq_search(params: dict) -> ToolResult:
    """Execute a hybrid (dense + sparse) search over the FAQ index."""
    query = params.get("query", "")
    domain_filter = params.get("domain")

    if not query.strip():
        return ToolResult(
            tool_name="faq_search",
            success=False,
            error_message="查询内容不能为空",
        )

    # Lazily import the hybrid retriever to avoid circular imports at module level.
    try:
        from app.rag.retriever import hybrid_retriever

        results = await hybrid_retriever.retrieve(
            query=query,
            domain=domain_filter,
        )
        return ToolResult(
            tool_name="faq_search",
            success=True,
            data={
                "query": query,
                "domain": domain_filter,
                "results": results,
                "total": len(results),
            },
        )
    except ImportError:
        # Degrade gracefully when the retriever is not wired up yet.
        return ToolResult(
            tool_name="faq_search",
            success=False,
            error_message="知识库检索模块尚未就绪，请稍后再试",
        )
    except Exception as exc:
        return ToolResult(
            tool_name="faq_search",
            success=False,
            error_message=f"知识库检索异常: {exc}",
        )
