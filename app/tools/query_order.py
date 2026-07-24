"""Order query tool using the logistics database."""

import json
from pathlib import Path

from app.agent.types import ToolResult
from app.tools.registry import tool_registry
from app.core.config import get_app_config

_DB_PATH = Path(__file__).parent.parent.parent / "knowledge_base" / "logistics_db.json"

def _load_db() -> list[dict]:
    """Load the logistics database."""
    try:
        with open(_DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _format_order(order: dict) -> str:
    """Format a single order into readable text for the LLM."""
    th = order.get("tracking_history", [])
    tracking_lines = "\n".join(
        f"    {t['time']}  {t['status']}  [{t.get('location', '')}]"
        for t in th[-4:]  # Last 4 tracking events only
    )

    return (
        f"订单号: {order['order_id']}\n"
        f"商品: {order['product']}\n"
        f"金额: ¥{order['amount']:.2f}\n"
        f"状态: {order['status']}\n"
        f"物流公司: {order.get('logistics_company', '未知')}\n"
        f"快递单号: {order.get('tracking_number', '暂无')}\n"
        f"下单时间: {order.get('created_at', '')}\n"
        f"预计送达: {order.get('estimated_delivery', '')}\n"
        f"物流详情:\n{tracking_lines}"
    )


@tool_registry.register(
    name="query_order",
    domain="order",
    description="查询用户订单及物流信息，支持按订单号、手机号或关键词检索。返回订单详情和完整物流轨迹。",
    params_schema={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "订单号，如 ORD20240715001"},
            "phone": {"type": "string", "description": "手机号，支持后四位匹配"},
            "query": {"type": "string", "description": "搜索关键词，匹配商品名称"},
        },
    },
)
async def query_order(params: dict) -> ToolResult:
    """Query orders from the logistics database."""
    if get_app_config().app.mode != "demo":
        return ToolResult(
            tool_name="query_order",
            success=False,
            error_message="生产环境订单适配器尚未配置",
        )
    order_id = params.get("order_id", "").strip()
    phone = params.get("phone", "").strip()
    query = params.get("query", "").strip()

    # Auto-extract order ID from query text if not explicitly provided
    if not order_id and query:
        import re
        m = re.search(r'ORD\d{6,}', query, re.IGNORECASE)
        if m:
            order_id = m.group()

    db = _load_db()
    results = []

    # Priority: order_id exact match
    if order_id:
        for order in db:
            if order["order_id"].upper() == order_id.upper():
                results.append(order)
                break

    # Phone match
    elif phone:
        for order in db:
            stored_phone = order.get("user_phone", "")
            if phone in stored_phone or stored_phone.endswith(phone[-4:]):
                results.append(order)

    # Keyword search in product name
    elif query:
        for order in db:
            if query in order.get("product", ""):
                results.append(order)

    # Build formatted data
    formatted_orders = []
    for order in results:
        formatted_orders.append({
            "order_id": order["order_id"],
            "product": order["product"],
            "amount": order["amount"],
            "status": order["status"],
            "logistics_company": order.get("logistics_company", "未知"),
            "tracking_number": order.get("tracking_number", ""),
            "created_at": order.get("created_at", ""),
            "estimated_delivery": order.get("estimated_delivery", ""),
            "tracking_history": order.get("tracking_history", []),
            "detail_text": _format_order(order),
        })

    return ToolResult(
        tool_name="query_order",
        success=True,
        data={
            "orders": formatted_orders,
            "total": len(formatted_orders),
            "summary_text": (
                "\n\n---\n\n".join(o["detail_text"] for o in formatted_orders)
                if formatted_orders
                else "未找到匹配订单，请核对订单号或手机号。"
            ),
            "is_demo_data": True,
            "data_mode": "legacy_mock",
            "privacy_notice": "演示数据不返回收货人姓名、手机号或详细地址。",
        },
    )
