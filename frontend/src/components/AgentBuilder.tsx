import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createAgent } from "../api/agents";
import { AgentDefinition } from "../api/types";

interface AgentBuilderProps {
  onCreated: (agent: AgentDefinition) => void;
}

const AgentBuilder = ({ onCreated }: AgentBuilderProps) => {
  const [requirement, setRequirement] = useState("");
  const [isComposite, setIsComposite] = useState(false);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createAgent,
    onSuccess: agent => {
      onCreated(agent);
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    }
  });

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!requirement.trim()) {
      return;
    }
    mutation.mutate({ user_requirement: requirement.trim(), is_composite: isComposite });
  };

  return (
    <section className="card">
      <header className="card-header">
        <h2>Step 1 · 创建 Agent</h2>
        <p>描述你想要的 agent，Meta Agent 会自动生成配置并缓存。</p>
      </header>
      <form onSubmit={handleSubmit} className="form">
        <label htmlFor="requirement">Agent 需求</label>
        <textarea
          id="requirement"
          value={requirement}
          onChange={event => setRequirement(event.target.value)}
          placeholder="例如：需要一个能帮我做市场调研并计算预算的agent"
          rows={4}
          required
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={isComposite}
            onChange={e => setIsComposite(e.target.checked)}
          />
          <span>是否使用 Multi-Agent（复合 Agent）</span>
        </label>
        <div className="actions">
          <button type="submit" disabled={mutation.isLoading}>
            {mutation.isLoading ? "创建中..." : "生成 Agent"}
          </button>
        </div>
      </form>
      {mutation.isSuccess && mutation.data && (
        <div className="result">
          <h3>{mutation.data.name}</h3>
          <p className="muted">{mutation.data.description}</p>
          <div className="meta">
            <strong>工具</strong>
            <ul>
              {mutation.data.tools.map(tool => (
                <li key={tool.name}>{tool.name}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {mutation.isError && (
        <p className="error">创建失败，请稍后重试。</p>
      )}
    </section>
  );
};

export default AgentBuilder;
