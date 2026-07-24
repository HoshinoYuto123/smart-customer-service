from pathlib import Path


STATIC = Path(__file__).parents[2] / "app" / "static"


def test_customer_service_shell_exposes_mvp_loop():
    html = (STATIC / "chat.html").read_text(encoding="utf-8")
    assert "选择服务对象" in html
    assert "快速办理" in html
    assert "查找答案" in html
    assert "智能客服" in html
    assert "转人工 / 提交工单" in html
    assert "服务进度" in html
    assert "MOCK 数据" in html
    assert 'src="/static/js/app.js' in html
    assert "<style>" not in html


def test_agent_shell_is_separate_and_explicitly_demo():
    html = (STATIC / "agent.html").read_text(encoding="utf-8")
    assert "客服工作台" in html
    assert "演示角色 · AGENT" in html
    assert 'src="/static/js/agent.js' in html


def test_frontend_has_accessibility_and_responsive_contracts():
    html = (STATIC / "chat.html").read_text(encoding="utf-8")
    css = (STATIC / "support.css").read_text(encoding="utf-8")
    assert "aria-live" in html
    assert "aria-label" in html
    assert "focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "@media (max-width: 640px)" in css
