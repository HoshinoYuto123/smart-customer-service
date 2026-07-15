"""Mock create-ticket tool – generates a support ticket ID."""

import random
import uuid
from datetime import datetime

from app.agent.types import ToolResult
from app.tools.registry import tool_registry

_TICKET_PRIORITIES = ["低", "中", "高", "紧急"]
_TICKET_CATEGORIES = [
    "订单问题",
    "账户问题",
    "退款申请",
    "技术故障",
    "投诉建议",
    "其他",
]


@tool_registry.register(
    name="create_ticket",
    domain="global",
    description="创建支持工单，记录用户问题并生成工单号",
    params_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "工单标题，简要描述问题",
            },
            "description": {
                "type": "string",
                "description": "问题详细描述",
            },
            "priority": {
                "type": "string",
                "description": "优先级: 低/中/高/紧急",
                "enum": _TICKET_PRIORITIES,
            },
            "category": {
                "type": "string",
                "description": "问题分类",
                "enum": _TICKET_CATEGORIES,
            },
        },
        "required": ["title", "description"],
    },
)
async def create_ticket(params: dict) -> ToolResult:
    """Create a support ticket and return the ticket ID."""
    title = params.get("title", "").strip()
    description = params.get("description", "").strip()
    priority = params.get("priority", "中")
    category = params.get("category", "其他")

    if not title:
        return ToolResult(
            tool_name="create_ticket",
            success=False,
            error_message="工单标题不能为空",
        )

    import asyncio
    await asyncio.sleep(random.uniform(0.1, 0.3))

    ticket_id = f"TK{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    return ToolResult(
        tool_name="create_ticket",
        success=True,
        data={
            "ticket_id": ticket_id,
            "title": title,
            "priority": priority,
            "category": category,
            "status": "待处理",
            "created_at": datetime.now().isoformat(),
            "estimated_response_time": "2小时内",
        },
    )
