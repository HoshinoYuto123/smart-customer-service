"""Policy / rule search tool – returns relevant policy snippets for queries."""

import random

from app.agent.types import ToolResult
from app.tools.registry import tool_registry

# Mock policy database indexed by keyword
_MOCK_POLICIES: list[dict] = [
    {
        "policy_id": "POL-001",
        "title": "退换货政策",
        "category": "售后",
        "snippet": "自签收之日起7天内，商品保持完好且不影响二次销售的情况下，可申请无理由退换货。"
        "食品、定制商品等特殊商品除外。退货运费由用户承担（质量问题除外）。",
        "effective_date": "2024-01-01",
    },
    {
        "policy_id": "POL-002",
        "title": "退款时效规则",
        "category": "售后",
        "snippet": "退货商品签收后1-3个工作日内完成质检，质检通过后原路退款。"
        "银行卡退款到账时间3-7个工作日，支付宝/微信退款即时到账。",
        "effective_date": "2024-03-15",
    },
    {
        "policy_id": "POL-003",
        "title": "会员积分规则",
        "category": "账户",
        "snippet": "每消费1元积1分，积分有效期为获得之日起12个月。"
        "积分可用于兑换优惠券、实物礼品或抵扣部分订单金额。"
        "不同会员等级享受不同倍数的积分加速权益。",
        "effective_date": "2024-01-01",
    },
    {
        "policy_id": "POL-004",
        "title": "隐私与数据保护政策",
        "category": "账户",
        "snippet": "我们严格遵守《个人信息保护法》，仅在提供服务所必需的范围内收集和使用您的个人信息。"
        "您可以随时在账户设置中查看、修改或删除您的个人信息。"
        "未经您的明确同意，我们不会将您的信息分享给第三方。",
        "effective_date": "2024-06-01",
    },
    {
        "policy_id": "POL-005",
        "title": "订单取消规则",
        "category": "订单",
        "snippet": "未付款订单将在24小时后自动取消。已付款但未发货的订单可随时申请取消，全额退款。"
        "已发货订单需在收货后发起退货流程。预售商品定金不支持退款。",
        "effective_date": "2024-01-01",
    },
    {
        "policy_id": "POL-006",
        "title": "配送时效说明",
        "category": "订单",
        "snippet": "国内主要城市次日达，偏远地区3-5个工作日。"
        "如遇恶劣天气、节假日等不可抗力因素，配送时效可能延迟1-3天。"
        "生鲜商品全程冷链配送，确保新鲜度。",
        "effective_date": "2024-01-01",
    },
]


@tool_registry.register(
    name="policy_search",
    domain="global",
    description="检索平台政策与规则，如退换货、退款、会员积分、隐私政策等",
    params_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "政策检索关键词，如 '退换货'、'退款'、'积分'",
            },
            "category": {
                "type": "string",
                "description": "可选分类过滤: 售后/账户/订单",
            },
        },
        "required": ["query"],
    },
)
async def policy_search(params: dict) -> ToolResult:
    """Search mock policy database and return matching snippets."""
    query = params.get("query", "").strip()
    category = params.get("category", "").strip()

    if not query:
        return ToolResult(
            tool_name="policy_search",
            success=False,
            error_message="请提供检索关键词",
        )

    import asyncio
    await asyncio.sleep(random.uniform(0.05, 0.15))

    # Simple keyword matching against title and snippet
    query_lower = query.lower()
    matched = []
    for policy in _MOCK_POLICIES:
        if category and policy["category"] != category:
            continue
        text = f"{policy['title']} {policy['snippet']}".lower()
        if any(word in text for word in query_lower.split()):
            matched.append(policy)

    if not matched:
        # Fallback: return a general policy
        matched = _MOCK_POLICIES[:2]

    return ToolResult(
        tool_name="policy_search",
        success=True,
        data={
            "query": query,
            "category": category,
            "results": matched,
            "total": len(matched),
        },
    )
