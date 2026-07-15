"""Order query tool using the logistics database."""

import json
import random
from pathlib import Path
from datetime import datetime, timedelta

from app.agent.types import ToolResult
from app.tools.registry import tool_registry

_DB_PATH = Path(__file__).parent.parent.parent / "knowledge_base" / "logistics_db.json"

# Fallback products for random generation
_PRODUCTS = ["智能音箱 Pro", "无线蓝牙耳机", "便携充电宝 20000mAh", "机械键盘 红轴", "4K显示器 27寸"]
_STATUSES = ["待付款", "已付款", "配送中", "已送达", "已取消", "退款中", "已完成"]


def _load_db() -> list[dict]:
    """Load the logistics database."""
    try:
        with open(_DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _random_order(order_id: str) -> dict:
    """Fallback: generate a random order if not in database."""
    return {
        "order_id": order_id,
        "status": random.choice(_STATUSES),
        "product": random.choice(_PRODUCTS),
        "amount": round(random.uniform(29.9, 2999.0), 2),
        "logistics_company": random.choice(["顺丰速运", "中通快递", "圆通速递", "京东物流"]),
        "tracking_number": f"SF{random.randint(1000000000, 9999999999)}",
        "created_at": (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d %H:%M:%S"),
        "estimated_delivery": (datetime.now() + timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d"),
        "receiver_name": "用户",
        "receiver_address": "地址信息未记录",
        "tracking_history": [
            {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "订单已创建", "location": "系统"}
        ],
    }


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
        f"收货人: {order.get('receiver_name', '')}\n"
        f"收货地址: {order.get('receiver_address', '')}\n"
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
        if not results:
            # Fallback: generate random order with given ID
            results.append(_random_order(order_id))

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

    # No specific params: return a few recent orders
    if not results:
        results = db[:2] if db else [_random_order("ORD000000")]

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
            "receiver_name": order.get("receiver_name", ""),
            "receiver_address": order.get("receiver_address", ""),
            "tracking_history": order.get("tracking_history", []),
            "detail_text": _format_order(order),
        })

    return ToolResult(
        tool_name="query_order",
        success=True,
        data={
            "orders": formatted_orders,
            "total": len(formatted_orders),
            "summary_text": "\n\n---\n\n".join(o["detail_text"] for o in formatted_orders),
        },
    )
