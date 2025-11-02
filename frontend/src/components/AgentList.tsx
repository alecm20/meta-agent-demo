import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAgent, fetchAgents } from "../api/agents";
import { AgentSummary } from "../api/types";

interface AgentListProps {
  selectedAgentId: string | null;
  onSelect: (agentId: string) => void;
}

const AgentList = ({ selectedAgentId, onSelect }: AgentListProps) => {
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["agents"],
    queryFn: fetchAgents
  });

  const delMutation = useMutation({
    mutationFn: (agentId: string) => deleteAgent(agentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    }
  });

  return (
    <section className="card">
      <header className="card-header">
        <h2>Step 2 · 已创建的 Agents</h2>
        <p>选择一个已有 agent，查看详情并执行任务。</p>
      </header>
      {isLoading && <p className="muted">加载中...</p>}
      {isError && <p className="error">获取 agent 列表失败。</p>}
      {data && data.length === 0 && <p className="muted">暂无 agent，先创建一个吧。</p>}
      {data && data.length > 0 && (
        <ul className="agent-list">
          {data.map((agent: AgentSummary) => (
            <li key={agent.agent_id} className={agent.agent_id === selectedAgentId ? "agent-item selected" : "agent-item"}>
              <div className="agent-item-header" onClick={() => onSelect(agent.agent_id)} role="button" tabIndex={0} onKeyPress={e => { if (e.key === "Enter") onSelect(agent.agent_id); }}>
                <h3>{agent.name}</h3>
                {agent.tools.length > 0 && (
                  <span className="badge">{agent.tools.join(", ")}</span>
                )}
              </div>
              <p className="muted">{agent.description}</p>
              <div className="actions">
                <button
                  className="danger"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("确认删除该 Agent 吗？该操作不可恢复。")) {
                      delMutation.mutate(agent.agent_id);
                    }
                  }}
                  disabled={delMutation.isLoading}
                >
                  {delMutation.isLoading ? "删除中..." : "删除"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default AgentList;
