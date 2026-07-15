from __future__ import annotations

import pytest
from app.agent.state import AgentState
from app.agent.graph import route_after_clarify, route_after_execute


class TestGraphRouting:
    def test_route_after_clarify_needs_clarify(self):
        state: AgentState = {
            "final_response": {"text": "请问您说的是哪个？", "action": "clarify"},
            "clarify_count": 1,
        }
        assert route_after_clarify(state) == "clarify_response"

    def test_route_after_clarify_ready(self):
        state: AgentState = {
            "final_response": None,
            "clarify_count": 0,
        }
        assert route_after_clarify(state) == "ready"

    def test_route_after_clarify_give_up(self):
        state: AgentState = {
            "final_response": None,
            "clarify_count": 2,
        }
        assert route_after_clarify(state) == "give_up"

    def test_route_after_execute_ready(self):
        state: AgentState = {
            "error_history": [],
            "router_result": {"suggested_tools": ["faq_search"]},
            "tool_calls": [{"tool": "faq_search", "params": {}}],
        }
        assert route_after_execute(state) == "ready"

    def test_route_after_execute_error(self):
        state: AgentState = {
            "error_history": [{"error": "e1"}, {"error": "e2"}, {"error": "e3"}],
            "router_result": {},
            "tool_calls": [],
        }
        assert route_after_execute(state) == "error"

    def test_route_after_execute_no_suggested_tools(self):
        state: AgentState = {
            "error_history": [],
            "router_result": {},
            "tool_calls": [],
        }
        assert route_after_execute(state) == "ready"
