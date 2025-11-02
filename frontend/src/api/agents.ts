import { apiClient } from "./client";
import {
  AgentCreateRequest,
  AgentDefinition,
  AgentSummary,
  TaskRequest,
  TaskResponse
} from "./types";

export const createAgent = async (
  payload: AgentCreateRequest
): Promise<AgentDefinition> => {
  const { data } = await apiClient.post<AgentDefinition>("/agents", payload);
  return data;
};

export const fetchAgents = async (): Promise<AgentSummary[]> => {
  const { data } = await apiClient.get<AgentSummary[]>("/agents");
  return data;
};

export const fetchAgent = async (agentId: string): Promise<AgentDefinition> => {
  const { data } = await apiClient.get<AgentDefinition>(`/agents/${agentId}`);
  return data;
};

export const runTask = async (
  agentId: string,
  payload: TaskRequest
): Promise<TaskResponse> => {
  const { data } = await apiClient.post<TaskResponse>(
    `/agents/${agentId}/tasks`,
    payload
  );
  return data;
};

export const deleteAgent = async (agentId: string): Promise<void> => {
  await apiClient.delete(`/agents/${agentId}`);
};
