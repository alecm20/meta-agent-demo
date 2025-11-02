from __future__ import annotations

import re
import json
from dataclasses import dataclass
from typing import List
from loguru import logger
from ..models.agent import AgentDefinition, TaskResponse, ToolCallTrace, ToolName
from .openai_client import get_openai_client
from .tools import ToolBox, ToolExecutionError

_CALC_PATTERN = re.compile(
    r"(?:calc(?:ulate)?|计算|算|求)(?:[^\d\(\)\+\-\*/]*)([\d\s\+\-\*/\.\(\)]+)",
    flags=re.IGNORECASE,
)



class TaskRunner:
    def __init__(self) -> None:
        self._client = get_openai_client()

    async def run(self, agent: AgentDefinition, task: str) -> TaskResponse:
        # Composite flow: multi-step LLM-only orchestration
        if getattr(agent, "is_composite", False):
            result, traces = await self._run_composite(agent, task)
            return TaskResponse(
                agent_id=agent.agent_id,
                task=task,
                result=result,
                tool_traces=traces,
                raw_response=result,
            )

        tool_box = ToolBox(agent.tools)
        tool_parameters = {config.name: config.parameters for config in agent.tools}
        traces: List[ToolCallTrace] = []
        contextual_notes: List[str] = []

        plan = await self._plan_tool_usage(
            agent, task, tool_box.available_tool_names, tool_parameters
        )

        for call in plan:
            tool_name = call.tool
            query = call.query
            reason = call.reason
            try:
                output = await tool_box.run(tool_name, query)
                traces.append(
                    ToolCallTrace(
                        tool=tool_name,
                        input=query,
                        output=output,
                    )
                )
                note_prefix = reason or f"{tool_name.value} result"
                contextual_notes.append(f"{note_prefix}: {output}")
            except ToolExecutionError as exc:
                traces.append(
                    ToolCallTrace(
                        tool=tool_name,
                        input=query,
                        output="",
                        succeeded=False,
                        error=str(exc),
                    )
                )
                note_prefix = reason or f"{tool_name.value} error"
                contextual_notes.append(f"{note_prefix}: {exc}")

        final_message, raw_response = await self._compose_final_response(agent, task, contextual_notes)

        return TaskResponse(
            agent_id=agent.agent_id,
            task=task,
            result=final_message,
            tool_traces=traces,
            raw_response=raw_response,
        )

    async def _run_composite(self, agent: AgentDefinition, task: str) -> tuple[str, List[ToolCallTrace]]:
        """Generic composite orchestration: plan -> execute steps -> assemble.

        Steps may use available tools or pure LLM generations. No domain hardcoding.
        """
        client = self._client
        traces: List[ToolCallTrace] = []
        if client is None:
            return ("[复合执行需要 LLM 支持]\n" + task, traces)

        # Describe available tools to the planner
        available: List[str] = []
        for cfg in agent.tools:
            available.append(f"- {cfg.name.value}: {cfg.description}")
        available_desc = "\n".join(available) if available else "(无工具，可纯LLM执行)"

        planner_system = (
            "You are an orchestration planner. Given a user goal and available tools, "
            "produce a minimal step plan in strict JSON. Each step has: "
            "{ title, action, input, tool? }. action in ['use_tool','llm_generate']. "
            "If a suitable tool exists, prefer 'use_tool'; otherwise use 'llm_generate'."
        )
        planner_user = (
            f"Goal: {task}\nAvailable tools:\n{available_desc}\n"
            "Return JSON with field steps: [{title, action, input, tool?}] only."
        )

        plan_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": planner_system},
                {"role": "user", "content": planner_user},
            ],
        )
        plan_content = plan_resp.choices[0].message.content if plan_resp.choices else "{}"
        logger.info("[Composite] Plan raw: {}", plan_content)
        try:
            plan_json = json.loads(plan_content)
        except Exception:
            start = plan_content.find("{")
            end = plan_content.rfind("}")
            plan_json = json.loads(plan_content[start:end+1]) if start != -1 and end != -1 else {"steps": []}
        steps = plan_json.get("steps") or []

        # Execute steps
        tool_box = ToolBox(agent.tools)
        executed_sections: List[str] = []
        for step in steps:
            title = step.get("title") or "步骤"
            action = (step.get("action") or "").lower()
            input_payload = step.get("input") or ""
            if action == "use_tool":
                tool_raw = step.get("tool")
                try:
                    tool_enum = ToolName(tool_raw) if tool_raw else None
                except Exception:
                    tool_enum = None
                if tool_enum is None:
                    executed_sections.append(f"## {title}\n\n(计划缺少有效工具，跳过)")
                    continue
                try:
                    output = await tool_box.run(tool_enum, str(input_payload))
                    traces.append(ToolCallTrace(tool=tool_enum, input=str(input_payload), output=output))
                    executed_sections.append(f"## {title}\n\n{output}")
                except ToolExecutionError as exc:
                    traces.append(ToolCallTrace(tool=tool_enum, input=str(input_payload), output="", succeeded=False, error=str(exc)))
                    executed_sections.append(f"## {title}\n\n(工具执行失败) {exc}")
            else:
                # LLM generation step
                gen_resp = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": agent.prompt},
                        {"role": "user", "content": f"任务: {title}\n指引: {input_payload}"},
                    ],
                )
                content = gen_resp.choices[0].message.content if gen_resp.choices else ""
                executed_sections.append(f"## {title}\n\n{content}")

        # Assemble final answer via LLM for coherence
        assembled_notes = "\n\n".join(executed_sections) if executed_sections else "(无步骤执行结果)"
        final_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "system", "content": agent.prompt},
                {"role": "user", "content": f"总体目标: {task}\n步骤结果:\n{assembled_notes}\n请整合为最终回答（使用 Markdown）。"},
            ],
        )
        final = final_resp.choices[0].message.content if final_resp.choices else assembled_notes
        return final or assembled_notes, traces

    async def _compose_final_response(
        self, agent: AgentDefinition, task: str, contextual_notes: List[str]
    ) -> tuple[str, str | None]:
        client = self._client
        if client is None:
            if contextual_notes:
                return "\n".join(contextual_notes), None
            return (
                "OpenAI API key is not configured. Provide one to enable natural language outputs.",
                None,
            )

        try:
            notes_section = "\n".join(contextual_notes) if contextual_notes else "无额外上下文"
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.4,
                messages=[
                    {"role": "system", "content": agent.prompt},
                    {
                        "role": "user",
                        "content": (
                            f"任务: {task}\n"
                            f"工具执行记录: {notes_section}\n"
                            "请基于任务与工具结果给出最终回答。"
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content if response.choices else None
            if not content:
                logger.error("LLM returned empty content when composing final response")
                return "未能生成回答，请稍后重试。", None
            return content, content
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to compose final response via OpenAI: %s", exc)
            if contextual_notes:
                return "\n".join(contextual_notes), None
            return "LLM 调用失败，且没有工具结果可用。", None

    async def _plan_tool_usage(
        self,
        agent: AgentDefinition,
        task: str,
        available_tools: List[ToolName],
        tool_parameters: dict[ToolName, dict],
    ) -> List["PlannedCall"]:
        if not available_tools:
            return []

        client = self._client
        auto_search = bool(tool_parameters.get(ToolName.web_search, {}).get("auto_search"))
        strategy = tool_parameters.get(ToolName.web_search, {}).get("strategy")

        if client is None:
            return self._heuristic_plan(task, available_tools, auto_search)

        system_prompt = (
            "You are a planning assistant. Decide how the agent should solve the user's request. "
            "Available tools:\n"
        )
        for tool in available_tools:
            description = ""
            if tool is ToolName.calculator:
                description = "calculator: evaluate arithmetic expressions."
            elif tool is ToolName.web_search:
                description = (
                    "web_search: query Google Programmable Search to gather fresh information."
                )
            elif tool is ToolName.amap_weather:
                description = "amap_weather: query live or forecast weather by city via AMap."
            system_prompt += f"- {tool.value}: {description}\n"
        system_prompt += (
            "Respond with JSON containing `should_use_tools` (boolean) and `tool_calls` "
            "(list of objects with fields `tool`, `query`, `reason`). Use the fewest necessary tool calls. "
            "If tools are unnecessary, return `should_use_tools: false` and an empty list."
        )

        user_prompt = (
            f"Agent persona: {agent.name}\n"
            f"Task: {task}\n"
            f"Auto search enabled: {auto_search}\n"
            f"Search strategy hint: {strategy or 'default'}"
        )

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content if response.choices else None
            if not content:
                raise ValueError("Empty planning response")
            plan_payload = json.loads(content)
            if not plan_payload.get("should_use_tools", True):
                return []
            tool_calls = plan_payload.get("tool_calls") or []
            planned_calls: List[PlannedCall] = []
            for item in tool_calls:
                tool_raw = item.get("tool")
                query = item.get("query")
                reason = item.get("reason", "")
                if not tool_raw or not query:
                    continue
                try:
                    tool_enum = ToolName(tool_raw)
                except ValueError:
                    continue
                if tool_enum not in available_tools:
                    continue
                planned_calls.append(PlannedCall(tool=tool_enum, query=query.strip(), reason=reason))
            if planned_calls:
                return planned_calls
        except Exception as exc:  # noqa: BLE001
            logger.exception("Planning via OpenAI failed: %s", exc)

        return self._heuristic_plan(task, available_tools, auto_search)

    def _heuristic_plan(
        self, task: str, available_tools: List[ToolName], auto_search: bool
    ) -> List["PlannedCall"]:
        plan: List[PlannedCall] = []
        # Minimal, non-hardcoded heuristic: if the agent provides a tool, use it directly
        if ToolName.web_search in available_tools:
            keyword = task.strip()
            if keyword:
                plan.append(
                    PlannedCall(
                        tool=ToolName.web_search,
                        query=keyword,
                        reason="使用检索工具获取与任务相关的最新信息",
                    )
                )

        if ToolName.calculator in available_tools:
            expression = _extract_expression(task)
            if expression:
                plan.append(
                    PlannedCall(
                        tool=ToolName.calculator,
                        query=expression,
                        reason="计算表达式结果以支持回答",
                    )
                )

        return plan


def _extract_expression(task: str) -> str | None:
    match = _CALC_PATTERN.search(task)
    if match:
        expression = match.group(1)
        return expression.replace("=", "").strip()
    standalone = re.fullmatch(r"[\d\s\+\-\*/\.\(\)]+", task.strip())
    if standalone:
        return task.strip()
    return None


def _extract_search_query(task: str) -> str | None:
    # Retained for compatibility, but fallback planner now uses full task as query when web_search exists
    return task.strip() or None


@dataclass
class PlannedCall:
    tool: ToolName
    query: str
    reason: str = ""
