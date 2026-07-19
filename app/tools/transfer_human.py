"""Transfer-to-human tool – sets the transfer flag for human hand-off."""


from app.agent.types import ToolResult
from app.tools.registry import tool_registry
from app.core.config import get_app_config


@tool_registry.register(
    name="transfer_human",
    domain="global",
    description="将当前会话转接至人工客服，适用于AI无法处理的复杂问题",
    params_schema={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "转人工的原因说明",
            },
            "summary": {
                "type": "string",
                "description": "当前问题的摘要，帮助人工客服快速了解情况",
            },
        },
        "required": ["reason"],
    },
)
async def transfer_human(params: dict) -> ToolResult:
    """Record a human-transfer request and return a confirmation."""
    if get_app_config().app.mode != "demo":
        return ToolResult(
            tool_name="transfer_human",
            success=False,
            error_message="生产环境人工队列适配器尚未配置",
        )
    reason = params.get("reason", "用户请求转接人工")
    summary = params.get("summary", "")

    return ToolResult(
        tool_name="transfer_human",
        success=True,
        data={
            "transferred": True,
            "reason": reason,
            "summary": summary,
            "message": "已为您转接人工客服，请稍候。当前排队人数: 2",
            "estimated_wait_seconds": 30,
            "is_demo_data": True,
        },
    )
