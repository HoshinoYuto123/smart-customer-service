"""Mock account query tool – generates realistic user account data."""

import random
from datetime import datetime, timedelta

from app.agent.types import ToolResult
from app.tools.registry import tool_registry

_MEMBERSHIP_LEVELS = ["普通会员", "银卡会员", "金卡会员", "钻石会员"]
_ACCOUNT_STATUSES = ["正常", "冻结", "待激活"]


def _random_account(user_id: str | None = None) -> dict:
    """Generate a single realistic mock account record."""
    if user_id is None:
        user_id = f"U{random.randint(100000, 999999):06d}"
    created_days = random.randint(30, 1095)
    return {
        "user_id": user_id,
        "nickname": f"用户_{user_id[-4:]}",
        "membership_level": random.choice(_MEMBERSHIP_LEVELS),
        "account_status": random.choice(_ACCOUNT_STATUSES),
        "balance": round(random.uniform(0, 5000.0), 2),
        "points": random.randint(0, 50000),
        "registered_at": (
            datetime.now() - timedelta(days=created_days)
        ).strftime("%Y-%m-%d"),
        "last_login": (
            datetime.now() - timedelta(hours=random.randint(1, 72))
        ).isoformat(),
        "bound_phone": f"138****{random.randint(1000, 9999)}",
        "bound_email": f"user{user_id[-4:]}@example.com",
    }


@tool_registry.register(
    name="query_account",
    domain="account",
    description="查询用户账户信息，包括会员等级、余额、积分、绑定信息等",
    params_schema={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "用户ID，格式如 U123456",
            },
            "phone": {
                "type": "string",
                "description": "绑定手机号",
            },
        },
    },
)
async def query_account(params: dict) -> ToolResult:
    """Return mock account data."""
    user_id = params.get("user_id", "").strip()
    phone = params.get("phone", "").strip()

    import asyncio
    await asyncio.sleep(random.uniform(0.1, 0.3))

    account = _random_account(user_id if user_id else None)
    if phone:
        account["bound_phone"] = phone

    return ToolResult(
        tool_name="query_account",
        success=True,
        data={"account": account},
    )
