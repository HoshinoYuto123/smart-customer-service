"""FAQ catalog for HTTP self-service discovery.

The existing JSON files are legacy demo content. Articles with unconfirmed
service hours or contact channels are excluded from customer-facing results.
PRD: CS-FN-003, CS-FN-004, CS-BR-003, CS-BR-004.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.support.models import FAQArticle


ROOT = Path(__file__).parent.parent.parent
FAQ_PATHS = [
    ROOT / "knowledge_base" / "global" / "global_faq.json",
    *sorted((ROOT / "knowledge_base" / "domains").glob("*/faqs/*_faq.json")),
]
EXCLUDED_ARTICLE_IDS = {"global_faq_002", "global_faq_003"}

CATEGORIES = [
    {"id": "order", "name": "订单与物流", "description": "查物流、修改或取消订单", "sort_order": 10},
    {"id": "payment", "name": "退款与支付", "description": "退款进度和支付异常", "sort_order": 20},
    {"id": "after_sale", "name": "退换与申诉", "description": "退换货、补发和投诉申诉", "sort_order": 30},
    {"id": "account", "name": "账号与安全", "description": "登录、密码和账号风险", "sort_order": 40},
    {"id": "course", "name": "课程与学习", "description": "课程权益、有效期和内容问题", "sort_order": 50},
    {"id": "global", "name": "其他帮助", "description": "服务说明和通用问题", "sort_order": 60},
]

COURSE_ARTICLES = [
    FAQArticle(
        id="course_faq_001",
        category_id="course",
        domain="course",
        question="如何查询课程有效期？",
        answer="进入客服首页并选择对应课程，再使用“课程有效期”自助工具。页面展示的是演示数据；真实有效期需要接入课程系统后确认。",
        keywords=["课程", "有效期", "权益", "学习"],
        data_mode="mock",
    ),
    FAQArticle(
        id="course_faq_002",
        category_id="course",
        domain="course",
        question="课程无法观看怎么办？",
        answer="先确认当前账号和课程对象，再检查网络与浏览器。若权益状态异常或排查后仍无法学习，请转人工并携带课程与错误信息。",
        keywords=["课程", "无法观看", "播放", "学习"],
        data_mode="mock",
    ),
]


@lru_cache()
def load_articles() -> tuple[FAQArticle, ...]:
    articles: list[FAQArticle] = []
    for path in FAQ_PATHS:
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in rows:
            if row.get("status") != "active" or row.get("id") in EXCLUDED_ARTICLE_IDS:
                continue
            domain = str(row.get("domain", "global"))
            articles.append(FAQArticle(
                id=str(row["id"]),
                category_id=domain if domain in {c["id"] for c in CATEGORIES} else "global",
                domain=domain,
                question=str(row.get("question", "")),
                answer=str(row.get("answer", "")),
                keywords=[str(item) for item in row.get("keywords", [])],
                related_faqs=[str(item) for item in row.get("related_faqs", [])],
                version=int(row.get("version", 1)),
                status="active",
                data_mode="legacy_demo",
            ))
    articles.extend(COURSE_ARTICLES)
    return tuple(articles)


def search_articles(query: str = "", category: str = "", *, limit: int = 20) -> list[FAQArticle]:
    query = query.strip().lower()
    scored: list[tuple[int, FAQArticle]] = []
    for article in load_articles():
        if category and article.category_id != category:
            continue
        haystack = " ".join([article.question, article.answer, *article.keywords]).lower()
        if not query:
            score = 1
        else:
            score = 4 * int(query in article.question.lower()) + 2 * int(query in haystack)
            score += sum(1 for token in article.keywords if token.lower() in query or query in token.lower())
        if score:
            scored.append((score, article))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [article for _, article in scored[:limit]]


def get_article(article_id: str) -> FAQArticle | None:
    return next((item for item in load_articles() if item.id == article_id), None)
