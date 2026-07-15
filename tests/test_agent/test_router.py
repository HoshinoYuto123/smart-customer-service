from __future__ import annotations

import pytest
from app.agent.nodes.router import _layer1_coarse_router


class TestLayer1Router:
    def test_order_keywords(self):
        scores = _layer1_coarse_router("我的订单怎么还没发货，物流信息查不到")
        assert scores["order"] > scores["account"]

    def test_payment_keywords(self):
        scores = _layer1_coarse_router("支付失败，余额扣了但订单没生成")
        assert scores["payment"] > 0

    def test_account_keywords(self):
        scores = _layer1_coarse_router("我想修改登录密码，手机号换了")
        assert scores["account"] > 0

    def test_after_sale_keywords(self):
        scores = _layer1_coarse_router("收到的商品有质量问题，想退货退款")
        assert scores["after_sale"] > 0

    def test_no_match_returns_low_scores(self):
        scores = _layer1_coarse_router("你好")
        assert all(s <= 0.1 for s in scores.values())

    def test_multi_domain(self):
        scores = _layer1_coarse_router("我支付了订单但是想退货退款")
        assert scores["payment"] > 0
        assert scores["after_sale"] > 0
