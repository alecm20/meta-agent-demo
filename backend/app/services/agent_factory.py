from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4
from loguru import logger
from ..models.agent import AgentDefinition, ToolConfig, ToolName
from .openai_client import get_openai_client, select_tools_via_llm
from .tools import validate_and_normalize_parameters


class AgentFactory:
    """Generates concrete agents from high-level user requirements."""

    def __init__(self) -> None:
        self._client = get_openai_client()

    async def create_agent(self, user_requirement: str) -> AgentDefinition:
        tool_configs = await self._select_tools(user_requirement)
        metadata = await self._generate_metadata(user_requirement, tool_configs)

        agent = AgentDefinition(
            agent_id=str(uuid4()),
            name=metadata["name"],
            description=metadata["description"],
            prompt=metadata["prompt"],
            tools=tool_configs,
            created_at=datetime.utcnow(),
        )
        return agent

    async def _select_tools(self, user_requirement: str) -> list[ToolConfig]:
        available_tools: list[dict[str, Any]] = [
            {
                "name": ToolName.calculator.value,
                "description": "Evaluate arithmetic expressions (+, -, *, /, parentheses).",
                "parameters_schema": {},
            },
            {
                "name": ToolName.web_search.value,
                "description": "Use Google Programmable Search to gather fresh web information.",
                "parameters_schema": {
                    "auto_search": {"type": "boolean", "optional": True},
                    "strategy": {"type": "string", "optional": True},
                    "search_params": {"type": "object", "optional": True},
                },
            },
            {
                "name": ToolName.amap_weather.value,
                "description": "Query live or forecast weather by city via AMap Web API.",
                "parameters_schema": {
                    "mode": {"type": "string", "enum": ["live", "forecast"], "optional": True}
                },
            },
        ]

        # Delegate to OpenAI helper
        tool_configs = await select_tools_via_llm(user_requirement, available_tools)
        # Normalize parameters according to tool schemas (LLM is source of truth)
        normalized: list[ToolConfig] = []
        for cfg in tool_configs:
            params = validate_and_normalize_parameters(cfg.name, cfg.parameters)
            normalized.append(ToolConfig(name=cfg.name, description=cfg.description, parameters=params))
        return normalized

    async def _generate_metadata(
        self, user_requirement: str, tool_configs: list[ToolConfig]
    ) -> dict[str, Any]:
        fallback = self._fallback_metadata(user_requirement, tool_configs)
        client = self._client
        if client is None:
            logger.warning("OpenAI API key not configured; using fallback metadata generation")
            return fallback

        tools_summary = [
            {
                "name": t.name.value,
                "description": t.description,
                "parameters": t.parameters or {},
            }
            for t in tool_configs
        ]
        prompt = (
            "你是资深AI系统设计师，请基于用户需求与可用工具，生成该agent的元数据。\n"
            "严格输出JSON，字段：\n"
            "- name: 简洁中文名（≤12字）\n"
            "- description: 清晰中文描述（≤50字），突出能力与适用范围\n"
            "- prompt: 作为system prompt，包含persona、工作流程、可用工具（名称与使用原则）\n"
            "不要输出多余文字或代码块标记。"
        )
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.2,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": (
                            f"用户需求: {user_requirement}\n"
                            f"可用工具(JSON): {json.dumps(tools_summary, ensure_ascii=False)}\n"
                            "请直接返回所需JSON。"
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content if response.choices else None
            logger.info("[AgentMetadata] Raw LLM content: {}", content)
            if not content:
                logger.error("Received empty response from OpenAI; using fallback metadata")
                return fallback

            metadata = self._try_parse_json(content)
            if metadata is None:
                logger.error("Failed to parse metadata JSON; using fallback")
                return fallback
            logger.info("[AgentMetadata] Parsed metadata: {}", json.dumps(metadata, ensure_ascii=False, indent=2))
            required_keys = {"name", "description", "prompt"}
            if not required_keys.issubset(metadata.keys()):
                logger.error("Missing keys in LLM metadata response; using fallback")
                return fallback
            return metadata  # type: ignore[return-value]
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to generate agent metadata via OpenAI: %s", exc)
            return fallback

    def _fallback_metadata(
        self, user_requirement: str, tool_configs: list[ToolConfig]
    ) -> dict[str, str]:
        joined_tools = ", ".join(tool.name.value for tool in tool_configs) if tool_configs else ""
        name = self._derive_friendly_name(user_requirement, tool_configs)
        description = self._compose_description(user_requirement, tool_configs, name)
        return {
            "name": name,
            "description": description,
            "prompt": (
                "You are a helpful assistant focused on the user's stated goal. "
                + (f"You may use these tools: {joined_tools}. " if joined_tools else "")
                + "When tools are insufficient or not provided, provide reasoned answers using your own knowledge."
            ),
        }

    def _derive_friendly_name(self, user_requirement: str, tool_configs: list[ToolConfig]) -> str:
        trimmed = user_requirement.strip()
        if trimmed:
            normalized = trimmed.replace("请", "").replace("帮我", "").replace("需要", "").strip()
            if len(normalized) <= 20:
                return normalized
        return "自定义 Agent"

    def _compose_description(
        self, user_requirement: str, tool_configs: list[ToolConfig], agent_name: str
    ) -> str:
        capability_sentence = "处理指定的任务"
        requirement = user_requirement.strip() or "用户的业务需求"
        tool_hint = ""
        if tool_configs:
            uniq = ", ".join(sorted({cfg.name.value for cfg in tool_configs}))
            tool_hint = f"（可用工具：{uniq}）"
        return f"{agent_name} {capability_sentence}{tool_hint}，适用于：{requirement}。"

    def _try_parse_json(self, content: str) -> dict[str, Any] | None:
        try:
            return json.loads(content)
        except Exception:
            # 尝试截取首尾花括号之间的JSON
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(content[start : end + 1])
                except Exception:
                    return None
            return None
