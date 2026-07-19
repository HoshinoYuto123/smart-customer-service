from app.rag.retriever import BM25Scorer, HybridRetriever


def test_chinese_bm25_matches_compound_words():
    scorer = BM25Scorer()
    scorer.index([
        {"question": "如何查询订单物流", "answer": "查看快递进度"},
        {"question": "如何修改登录密码", "answer": "进入安全中心"},
    ])
    hits = scorer.search("订单物流查询")
    assert hits
    assert hits[0][0] == 0


def test_hybrid_retriever_exposes_compatible_search_api():
    assert hasattr(HybridRetriever, "retrieve")
    assert hasattr(HybridRetriever, "search")
