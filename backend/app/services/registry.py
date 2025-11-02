from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

from ..models.agent import AgentDefinition


@dataclass
class _AgentRegistry:
    """In-memory agent registry with JSON persistence."""

    _agents: Dict[str, AgentDefinition]
    _store_path: Path

    @classmethod
    def create(cls) -> "_AgentRegistry":
        root = Path(__file__).resolve().parents[2]  # project root: backend/
        data_dir = root / "app" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        store_path = data_dir / "agents.json"
        registry = cls(_agents={}, _store_path=store_path)
        registry._load()
        return registry

    async def add(self, agent: AgentDefinition) -> None:
        self._agents[agent.agent_id] = agent
        self._save()

    async def get(self, agent_id: str) -> Optional[AgentDefinition]:
        return self._agents.get(agent_id)

    async def list(self) -> List[AgentDefinition]:
        return list(self._agents.values())

    async def delete(self, agent_id: str) -> bool:
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._save()
            return True
        return False

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            for item in raw:
                try:
                    agent = AgentDefinition.model_validate(item)
                    self._agents[agent.agent_id] = agent
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skip invalid agent in store: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load agents store: %s", exc)

    def _save(self) -> None:
        try:
            # Use JSON-safe dump to serialize datetimes as ISO strings
            payload = [agent.model_dump(mode="json") for agent in self._agents.values()]
            self._store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to save agents store: %s", exc)


# Singleton registry used by API layer
registry = _AgentRegistry.create()
