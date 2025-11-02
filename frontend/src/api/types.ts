export type ToolName = "calculator" | "web_search" | "amap_weather";

export interface ToolConfig {
  name: ToolName;
  description: string;
  parameters: Record<string, unknown>;
}

export interface AgentCreateRequest {
  user_requirement: string;
  is_composite?: boolean;
}

export interface AgentDefinition {
  agent_id: string;
  name: string;
  description: string;
  prompt: string;
  tools: ToolConfig[];
  created_at: string;
  is_composite: boolean;
  sub_agents: SubAgentSummary[];
}

export interface AgentSummary {
  agent_id: string;
  name: string;
  description: string;
  tools: ToolName[];
  created_at: string;
  is_composite: boolean;
}

export interface TaskRequest {
  task: string;
}

export interface ToolTrace {
  tool: ToolName;
  input: string;
  output: string;
  succeeded: boolean;
  error?: string | null;
}

export interface TaskResponse {
  agent_id: string;
  task: string;
  result: string;
  tool_traces: ToolTrace[];
  raw_response?: string | null;
  created_at: string;
}

export interface SubAgentSummary {
  agent_id?: string | null;
  name: string;
  description: string;
  tools: ToolName[];
}
