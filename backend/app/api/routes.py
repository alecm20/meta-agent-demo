from __future__ import annotations

from fastapi import APIRouter, HTTPException, status, Response
from ..models.agent import (
    AgentCreateRequest,
    AgentDefinition,
    AgentSummary,
    TaskRequest,
    TaskResponse,
)
from ..services.agent_factory import AgentFactory
from ..services.registry import registry
from ..services.task_runner import TaskRunner

router = APIRouter(prefix="/api")
agent_factory = AgentFactory()
task_runner = TaskRunner()


@router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/agents", response_model=AgentDefinition, tags=["agents"], status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreateRequest) -> AgentDefinition:
    agent = await agent_factory.create_agent(payload.user_requirement)
    # propagate composite flag for now (sub_agents 由后续 Planner 生成)
    agent.is_composite = payload.is_composite
    await registry.add(agent)
    return agent


@router.get("/agents", response_model=list[AgentSummary], tags=["agents"])
async def list_agents() -> list[AgentSummary]:
    agents = await registry.list()
    return [
        AgentSummary(
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            tools=[tool.name for tool in agent.tools],
            created_at=agent.created_at,
            is_composite=agent.is_composite,
        )
        for agent in agents
    ]


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["agents"])
async def delete_agent(agent_id: str) -> Response:
    deleted = await registry.delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/agents/{agent_id}", response_model=AgentDefinition, tags=["agents"])
async def get_agent(agent_id: str) -> AgentDefinition:
    agent = await registry.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.post("/agents/{agent_id}/tasks", response_model=TaskResponse, tags=["tasks"])
async def run_task(agent_id: str, payload: TaskRequest) -> TaskResponse:
    agent = await registry.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return await task_runner.run(agent, payload.task)
