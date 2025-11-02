from __future__ import annotations

from functools import lru_cache
from openai import AsyncOpenAI
from ..core.config import get_settings
from typing import Any
import json
from loguru import logger
from ..models.agent import ToolConfig, ToolName


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def select_tools_via_llm(
    user_requirement: str,
    available_tools: list[dict[str, Any]],
) -> list[ToolConfig]:
    """Ask the LLM to choose tools from the registry.

    available_tools: list of {name, description, parameters_schema}
    """
    client = get_openai_client()
    if client is None:
        # No model available; return no tools and let the system operate without tools
        return []

    system_prompt = (
        "You are an expert AI system architect. Given a user requirement and a list of available tools, "
        "select the minimal set of tools needed.\n"
        "Guidelines:\n"
        "- Arithmetic/numeric expressions -> prefer calculator.\n"
        "- Weather queries (城市天气/天气/forecast/live weather) -> choose amap_weather (parameters: mode=live or forecast).\n"
        "- News/search/research queries (新闻/资讯/头条/搜索/查询/检索) -> choose web_search.\n"
        "- Only choose web_search if fresh web information is required or explicitly implied.\n"
        "Return strict JSON with field `tools` which is a list of objects: {name, description, parameters?}.\n"
        "If no tool is needed, return an empty list."
    )

    try:
        available_tools_json = json.dumps(available_tools, ensure_ascii=False)
        output_hint = "\nOutput strict JSON with only the `tools` field."
        fewshot_user_weather = (
            "User requirement: 创建一个天气查询的agent，支持城市实时和未来天气预报\n"
            + "Available tools: "
            + available_tools_json
            + output_hint
        )
        fewshot_assistant_weather = {
            "tools": [
                {
                    "name": "amap_weather",
                    "description": "查询城市实时与预报天气",
                    "parameters": {"mode": "forecast"}
                }
            ]
        }
        fewshot_user_news = (
            "User requirement: 创建一个搜索新闻的agent，聚焦最新资讯和头条\n"
            + "Available tools: "
            + available_tools_json
            + output_hint
        )
        fewshot_assistant_news = {
            "tools": [
                {
                    "name": "web_search",
                    "description": "检索最新新闻和资讯",
                    "parameters": {"auto_search": True}
                }
            ]
        }

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": fewshot_user_weather},
                {"role": "assistant", "content": json.dumps(fewshot_assistant_weather, ensure_ascii=False)},
                {"role": "user", "content": fewshot_user_news},
                {"role": "assistant", "content": json.dumps(fewshot_assistant_news, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": (
                        "User requirement: "
                        + user_requirement
                        + "\nAvailable tools: "
                        + available_tools_json
                        + output_hint
                    ),
                },
            ],
        )
        content = response.choices[0].message.content if response.choices else None
        logger.info("[ToolSelection] Raw LLM content: {}", content)
        if not content:
            raise ValueError("Empty tool selection response")
        payload = json.loads(content)
        logger.info("[ToolSelection] Parsed payload: {}", json.dumps(payload, ensure_ascii=False, indent=2))
        selected = payload.get("tools") or []
        tool_configs: list[ToolConfig] = []
        allowed_names = {tool.get("name") for tool in available_tools if tool.get("name")}
        for item in selected:
            name = item.get("name")
            description = item.get("description") or ""
            params = item.get("parameters") or {}
            if name not in allowed_names:
                continue
            try:
                tool_enum = ToolName(name)
            except Exception:
                continue
            tool_configs.append(
                ToolConfig(name=tool_enum, description=description, parameters=params)
            )
        logger.info(
            "[ToolSelection] Final tool configs: {}",
            json.dumps([tc.model_dump() for tc in tool_configs], ensure_ascii=False, indent=2),
        )
        return tool_configs
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to select tools via OpenAI: %s", exc)
        # On error, return no tools rather than forcing a default
        return []
