import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchAgent, runTask } from "../api/agents";
import { TaskResponse } from "../api/types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface TaskRunnerProps {
  agentId: string | null;
}

const TaskRunner = ({ agentId }: TaskRunnerProps) => {
  const [task, setTask] = useState("");
  const [lastTask, setLastTask] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: agent, isLoading: loadingAgent } = useQuery({
    queryKey: ["agent", agentId],
    queryFn: () => fetchAgent(agentId as string),
    enabled: Boolean(agentId)
  });

  const mutation = useMutation({
    mutationFn: (payload: { task: string }) => runTask(agentId as string, payload),
    onSuccess: () => {
      setTask("");
      void queryClient.invalidateQueries({ queryKey: ["agent", agentId] });
    }
  });

  useEffect(() => {
    setTask("");
    mutation.reset();
  }, [agentId]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!agentId || !task.trim()) {
      return;
    }
    const trimmed = task.trim();
    setLastTask(trimmed);
    mutation.mutate({ task: trimmed });
  };

  if (!agentId) {
    return (
      <section className="card">
        <header className="card-header">
          <h2>Step 3 · 执行任务</h2>
        </header>
        <p className="muted">请选择一个 agent 后再执行任务。</p>
      </section>
    );
  }

  return (
    <section className="card">
      <header className="card-header">
        <h2>Step 3 · 执行任务</h2>
        {agent && <p>当前 Agent：{agent.name}</p>}
      </header>
      {loadingAgent && <p className="muted">agent 加载中...</p>}
      {agent && (
        <>
          <form onSubmit={handleSubmit} className="form">
            <label htmlFor="task">任务描述</label>
            <textarea
              id="task"
              value={task}
              onChange={event => setTask(event.target.value)}
              placeholder="例如：帮我计算 1200 + 365 的结果或者搜索 meta agent 的定义"
              rows={3}
              required
            />
            <div className="actions">
              <button type="submit" disabled={mutation.isLoading}>
                {mutation.isLoading ? "执行中..." : "提交任务"}
              </button>
            </div>
          </form>
          {mutation.isError && <p className="error">任务执行失败，请稍后重试。</p>}
          {mutation.isSuccess && mutation.data && (
            <TaskResultView result={mutation.data} lastTask={lastTask || undefined} />
          )}
        </>
      )}
    </section>
  );
};

interface TaskResultViewProps {
  result: TaskResponse;
  lastTask?: string;
}

const TaskResultView = ({ result, lastTask }: TaskResultViewProps) => {
  const toRenderableMarkdown = (raw: string): string => {
    const lines = raw.split("\n");
    if (lines.length === 0) return raw;
    // If the first line echoes the user's task as an H1, render it as a blockquote instead
    const first = lines[0];
    const stripped = first.replace(/^#\s+/, "").trim();
    if (lastTask && stripped === lastTask.trim()) {
      lines[0] = `> ${stripped}`;
      return lines.join("\n");
    }
    // Otherwise, if the first line is an H1 and looks like a restatement of the task prompt, demote to quote
    if (/^#\s+/.test(first)) {
      lines[0] = `> ${stripped}`;
      return lines.join("\n");
    }
    return raw;
  };

  const rendered = toRenderableMarkdown(result.result);
  return (
    <div className="result">
      <h3>执行结果</h3>
      <div className="markdown-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{rendered}</ReactMarkdown>
      </div>
      {result.tool_traces.length > 0 && (
        <div className="meta">
          <strong>工具调用</strong>
          <ul className="tool-trace-list">
            {result.tool_traces.map(trace => (
              <li key={`${trace.tool}-${trace.input}`} className={trace.succeeded ? "" : "error"}>
                <span className="badge">{trace.tool}</span>
                <div>
                  <p className="muted">输入：{trace.input}</p>
                  {trace.succeeded ? (
                    <p className="muted">输出：{trace.output}</p>
                  ) : (
                    <p className="error">错误：{trace.error}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {result.raw_response && (
        <details>
          <summary>原始响应</summary>
          <pre>{result.raw_response}</pre>
        </details>
      )}
    </div>
  );
};

export default TaskRunner;
