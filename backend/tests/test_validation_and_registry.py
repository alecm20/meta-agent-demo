from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.tools import validate_and_normalize_parameters
from app.models.agent import ToolName, AgentDefinition, ToolConfig
from app.services.registry import _AgentRegistry
from datetime import datetime


def test_validate_and_normalize_web_search_params():
    params = {
        "auto_search": "yes",
        "strategy": " financial_news ",
        "search_params": {"num": 5, "safe": "active", "hl": "zh-CN", 1: "bad"},
        "unknown": True,
    }
    normalized = validate_and_normalize_parameters(ToolName.web_search, params)
    assert normalized["auto_search"] is True
    assert normalized["strategy"] == "financial_news"
    assert isinstance(normalized.get("search_params"), dict)
    assert 1 not in normalized["search_params"]
    assert "unknown" not in normalized


def test_validate_and_normalize_calculator_params():
    normalized = validate_and_normalize_parameters(ToolName.calculator, {"x": 1})
    assert normalized == {}


def test_registry_add_get_list(tmp_path: Path):
    # construct isolated registry pointing at tmp store
    store_path = tmp_path / "agents.json"
    reg = _AgentRegistry(_agents={}, _store_path=store_path)
    agent = AgentDefinition(
        agent_id="a1",
        name="n",
        description="d",
        prompt="p",
        tools=[ToolConfig(name=ToolName.calculator, description="calc")],
        created_at=datetime.utcnow(),
    )

    async def flow():
        await reg.add(agent)
        got = await reg.get("a1")
        assert got is not None
        all_items = await reg.list()
        assert len(all_items) == 1

    asyncio.run(flow())


