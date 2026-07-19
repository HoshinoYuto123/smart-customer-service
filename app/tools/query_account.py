"""Mock account query tool – generates realistic user account data."""

import hashlib
from datetime import datetime, timedelta

from app.agent.types import ToolResult
from app.tools.registry import tool_registry
from app.core.config import get_app_config

_MEMBERSHIP_LEVELS = ["普通会员", "银卡会员", "金卡会员", "钻石会员"]
_ACCOUNT_STATUSES = ["正常", "冻结", "待激活"]


def _demo_account(user_id: str | None = None) -> dict:
    """Generate stable, clearly marked demo data for repeatable tests."""
    if user_id is None:
        user_id = "U000001"
    seed = int(hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8], 16)
    created_days = 30 + seed % 1065
    return {
        "user_id": user_id,
        "nickname": f"用户_{user_id[-4:]}",
        "membership_level": _MEMBERSHIP_LEVELS[seed % len(_MEMBERSHIP_LEVELS)],
        "account_status": _ACCOUNT_STATUSES[seed % len(_ACCOUNT_STATUSES)],
        "balance": round((seed % 500000) / 100, 2),
        "points": seed % 50000,
        "registered_at": (
            datetime.now() - timedelta(days=created_days)
        ).strftime("%Y-%m-%d"),
        "last_login": (
            datetime.now() - timedelta(hours=1 + seed % 72)
        ).isoformat(),
        "bound_phone": f"138****{1000 + seed % 9000}",
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
    if get_app_config().app.mode != "demo":
        return ToolResult(
            tool_name="query_account",
            success=False,
            error_message="生产环境账户适配器尚未配置",
        )
    user_id = params.get("user_id", "").strip()
    phone = params.get("phone", "").strip()

    account = _demo_account(user_id if user_id else None)
    if phone:
        account["bound_phone"] = phone

    return ToolResult(
        tool_name="query_account",
        success=True,
        data={"account": account, "is_demo_data": True},
    )
