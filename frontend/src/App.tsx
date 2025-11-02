import { useState } from "react";
import AgentBuilder from "./components/AgentBuilder";
import AgentList from "./components/AgentList";
import TaskRunner from "./components/TaskRunner";
import { AgentDefinition } from "./api/types";

const App = () => {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  const handleAgentCreated = (agent: AgentDefinition) => {
    setSelectedAgentId(agent.agent_id);
  };

  return (
    <main className="layout">
      <header className="page-header">
        <h1>Meta Agent Studio</h1>
        <p className="muted">
          通过元 agent 快速生成、管理和调用专属助手。先创建，再选择，最后执行任务。
        </p>
      </header>
      <div className="grid">
        <AgentBuilder onCreated={handleAgentCreated} />
        <AgentList selectedAgentId={selectedAgentId} onSelect={setSelectedAgentId} />
      </div>
      <TaskRunner agentId={selectedAgentId} />
    </main>
  );
};

export default App;
