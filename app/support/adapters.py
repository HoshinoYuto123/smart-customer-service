"""Replaceable external-service ports and centralized demo adapter.

No response from this module represents a real order, payment, course or
notification system. PRD: CS-DT-001 through CS-DT-017.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from app.support.models import Capability, SelfServiceStatus, SupportContext, SupportObject


CAPABILITIES = [
    Capability(id="logistics_query", title="查询物流", description="查看演示订单的物流节点", object_types=["order"]),
    Capability(id="order_modify", title="修改订单", description="提交演示修改申请", object_types=["order"], requires_confirmation=True),
    Capability(id="order_cancel", title="取消订单", description="提交演示取消申请", object_types=["order"], requires_confirmation=True),
    Capability(id="refund_apply", title="申请退款", description="创建演示退款服务记录", object_types=["order", "course"], requires_confirmation=True, risk="sensitive"),
    Capability(id="refund_status", title="退款进度", description="查询演示退款状态", object_types=["order", "course"]),
    Capability(id="exchange_reship", title="换货或补发", description="提交演示售后申请", object_types=["order"], requires_confirmation=True),
    Capability(id="password_reset", title="重置密码", description="进入安全验证说明，不接收密码或验证码", object_types=["account"], requires_confirmation=True, risk="security"),
    Capability(id="account_update", title="修改账号信息", description="提交演示账号资料变更请求", object_types=["account"], requires_confirmation=True, risk="security"),
    Capability(id="course_validity", title="课程有效期", description="查看演示课程权益", object_types=["course"]),
    Capability(id="course_restore", title="恢复课程权益", description="提交演示课程权益核验", object_types=["course"], requires_confirmation=True),
    Capability(id="invoice_contract", title="发票或合同", description="提交演示票据服务申请", object_types=["order", "course"], requires_confirmation=True),
    Capability(id="appeal_materials", title="提交申诉材料", description="创建可补充材料的演示工单", object_types=["order", "course", "account"], requires_confirmation=True),
    Capability(id="service_progress", title="查询服务进度", description="查看自助任务和工单时间线"),
]


class BusinessAdapter(Protocol):
    data_mode: str

    def get_context(self, user_id: str) -> SupportContext: ...
    def capabilities(self) -> list[Capability]: ...
    def execute_self_service(
        self,
        capability: str,
        *,
        user_id: str,
        object_type: str,
        object_id: str,
        payload: dict[str, Any],
    ) -> tuple[SelfServiceStatus, dict[str, Any], str]: ...
    def send_notification(self, *, user_id: str, event_type: str, content: str) -> dict[str, Any]: ...


@dataclass
class MockBusinessAdapter:
    """Deterministic, ownership-safe demo data.

    The generated objects are scoped to ``user_id`` and contain no real
    addresses, phone numbers, payment credentials or course accounts.
    """

    data_mode: str = "mock"

    @staticmethod
    def _suffix(user_id: str) -> str:
        return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8].upper()

    def get_context(self, user_id: str) -> SupportContext:
        suffix = self._suffix(user_id)
        objects = [
            SupportObject(
                id=f"DEMO-ORD-{suffix}",
                type="order",
                title="演示订单 · 无线耳机",
                subtitle="仅用于功能验证，不代表真实交易",
                status="配送中（演示）",
                meta={"tracking_code_masked": f"DEMO****{suffix[-4:]}", "owner_id": user_id},
            ),
            SupportObject(
                id=f"DEMO-COURSE-{suffix}",
                type="course",
                title="演示课程 · 产品体验设计",
                subtitle="仅用于功能验证，不代表真实课程权益",
                status="可学习（演示）",
                meta={"validity": "以真实课程系统为准", "owner_id": user_id},
            ),
            SupportObject(
                id=f"DEMO-ACCOUNT-{suffix}",
                type="account",
                title="当前演示账号",
                subtitle="敏感操作需接入真实安全验证",
                status="正常（演示）",
                meta={"owner_id": user_id},
            ),
        ]
        return SupportContext(
            user={
                "id": user_id,
                "display_name": "演示用户",
                "role": "user",
                "membership": "基础服务",
            },
            objects=objects,
            selected_object_id=objects[0].id,
            data_mode=self.data_mode,
        )

    def capabilities(self) -> list[Capability]:
        return [item.model_copy(deep=True) for item in CAPABILITIES]

    def execute_self_service(
        self,
        capability: str,
        *,
        user_id: str,
        object_type: str,
        object_id: str,
        payload: dict[str, Any],
    ) -> tuple[SelfServiceStatus, dict[str, Any], str]:
        if payload.get("simulate") == "failure":
            return SelfServiceStatus.FAILED, {}, "DEPENDENCY_UNAVAILABLE"
        if payload.get("simulate") == "timeout":
            return SelfServiceStatus.UNKNOWN, {"next_action": "create_ticket"}, "RESULT_UNKNOWN"

        now = datetime.now(timezone.utc).isoformat()
        base = {
            "data_mode": self.data_mode,
            "disclaimer": "这是演示结果，不会修改真实订单、资金、账号或课程数据。",
            "updated_at": now,
        }
        if capability == "logistics_query":
            base.update({
                "headline": "包裹正在运输中（演示）",
                "timeline": ["订单已创建", "包裹已揽收", "运输中"],
                "next_action": "如真实物流长时间未更新，请联系人工核验。",
            })
            return SelfServiceStatus.SUCCEEDED, base, ""
        if capability == "refund_status":
            base.update({"headline": "未找到进行中的演示退款", "next_action": "可发起退款申请或联系人工核验。"})
            return SelfServiceStatus.SUCCEEDED, base, ""
        if capability == "course_validity":
            base.update({"headline": "演示课程当前可学习", "validity": "真实有效期需由课程系统提供"})
            return SelfServiceStatus.SUCCEEDED, base, ""
        if capability == "service_progress":
            base.update({"headline": "服务进度已汇总", "next_action": "请在“服务进度”页面查看任务和工单。"})
            return SelfServiceStatus.SUCCEEDED, base, ""
        if capability == "password_reset":
            base.update({
                "headline": "需要安全验证",
                "next_action": "演示环境不接收密码或验证码，请转安全人工或接入真实认证系统。",
            })
            return SelfServiceStatus.INELIGIBLE, base, "SECURITY_VERIFICATION_REQUIRED"

        base.update({
            "headline": "演示申请已记录",
            "next_action": "需要真实业务系统确认资格和结果；当前不会执行真实操作。",
            "requires_ticket": capability in {"refund_apply", "exchange_reship", "appeal_materials", "course_restore"},
        })
        return SelfServiceStatus.SUCCEEDED, base, ""

    def send_notification(self, *, user_id: str, event_type: str, content: str) -> dict[str, Any]:
        return {
            "status": "sent",
            "channel": "in_app_mock",
            "data_mode": self.data_mode,
            "event_type": event_type,
        }
