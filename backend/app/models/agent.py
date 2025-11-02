from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ToolName(str, Enum):
    calculator = "calculator"
    web_search = "web_search"
    amap_weather = "amap_weather"


class ToolConfig(BaseModel):
    name: ToolName
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentCreateRequest(BaseModel):
    user_requirement: str = Field(..., min_length=3, description="描述想要创建的 agent")
    is_composite: bool = Field(default=False, description="是否为复合（multi-agent）")


class AgentDefinition(BaseModel):
    agent_id: str
    name: str
    description: str
    prompt: str
    tools: list[ToolConfig]
    created_at: datetime
    is_composite: bool = Field(default=False)
    sub_agents: list["SubAgentSummary"] = Field(default_factory=list)


class AgentSummary(BaseModel):
    agent_id: str
    name: str
    description: str
    tools: list[ToolName]
    created_at: datetime
    is_composite: bool = Field(default=False)


class ToolCallTrace(BaseModel):
    tool: ToolName
    input: str
    output: str
    succeeded: bool = True
    error: str | None = None


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=3, description="需要 agent 执行的任务")


class TaskResponse(BaseModel):
    agent_id: str
    task: str
    result: str
    tool_traces: list[ToolCallTrace] = Field(default_factory=list)
    raw_response: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SubAgentSummary(BaseModel):
    agent_id: str | None = None
    name: str
    description: str
    tools: list[ToolName]
